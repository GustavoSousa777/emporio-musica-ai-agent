"""Índice das políticas em arquivo e busca híbrida (BM25 + embeddings).

Fluxo:
  build_index()  : PDF -> chunks -> (embeddings, se houver chave e cota) -> JSON em disco
  Retriever.search(query, k): BM25 sempre; se o índice tem vetores e o modelo responde,
      funde os dois rankings com Reciprocal Rank Fusion. Qualquer falha de embedding
      (cota, rede, chave ausente) rebaixa a busca para só BM25, sem erro para o usuário.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.core.config import POLICIES_PDF, Settings, get_settings
from app.rag.embeddings import Embedder, GeminiEmbedder, cosine, embed_with_failover
from app.rag.ingestion import PolicyChunk, chunk_policy_pdf, file_sha256
from app.rag.lexical import BM25, document_tokens, query_terms

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
RRF_K = 60
# Piso heurístico de similaridade semântica para trechos sem nenhum termo em comum com a
# pergunta. Precisa ser calibrado com chave real (ver docs/rag.md).
DEFAULT_MIN_SEMANTIC = 0.45


@dataclass
class PolicyHit:
    chunk_id: str
    section: str
    title: str
    page: int
    text: str
    score: float
    lexical_score: float
    semantic_score: float | None

    def to_dict(self) -> dict:
        return {
            "section": self.section,
            "title": self.title,
            "page": self.page,
            "text": self.text,
            "score": round(self.score, 4),
            "lexical_score": round(self.lexical_score, 3),
            "semantic_score": None if self.semantic_score is None else round(self.semantic_score, 3),
        }


@dataclass
class PolicyIndex:
    chunks: list[PolicyChunk]
    vectors: list[list[float]] | None
    embedding_model: str | None
    embedding_dims: int | None
    source_sha256: str
    built_at: str

    @property
    def has_vectors(self) -> bool:
        return bool(self.vectors) and self.embedding_model is not None

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": INDEX_VERSION,
            "source_sha256": self.source_sha256,
            "built_at": self.built_at,
            "embedding": (
                {"model": self.embedding_model, "dims": self.embedding_dims} if self.has_vectors else None
            ),
            "chunks": [
                {**c.to_dict(), "vector": [round(x, 6) for x in self.vectors[i]] if self.has_vectors else None}
                for i, c in enumerate(self.chunks)
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "PolicyIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != INDEX_VERSION:
            raise ValueError("Versão de índice incompatível.")
        embedding = data.get("embedding")
        vectors = [c.pop("vector") for c in data["chunks"]] if embedding else None
        if not embedding:
            for c in data["chunks"]:
                c.pop("vector", None)
        return cls(
            chunks=[PolicyChunk.from_dict(c) for c in data["chunks"]],
            vectors=vectors,
            embedding_model=embedding["model"] if embedding else None,
            embedding_dims=embedding["dims"] if embedding else None,
            source_sha256=data["source_sha256"],
            built_at=data["built_at"],
        )


def _default_embedder_factory(settings: Settings) -> Callable[[str], Embedder] | None:
    if not settings.gemini_api_key:
        return None
    return lambda model: GeminiEmbedder(settings.gemini_api_key, model, dims=settings.embedding_dims)


def build_index(
    pdf_path: Path | str = POLICIES_PDF,
    index_path: Path | str | None = None,
    embedder_models: list[str] | tuple[str, ...] | None = None,
    make_embedder: Callable[[str], Embedder] | None = None,
    lexical_only: bool = False,
) -> PolicyIndex:
    """Extrai o PDF, gera embeddings (se possível) e grava o índice em arquivo.

    lexical_only=True nunca chama a API (usado nos testes e com RAG_MODE=lexical).
    """
    settings = get_settings()
    chunks = chunk_policy_pdf(pdf_path)
    vectors, embedder = None, None

    if not lexical_only:
        make_embedder = make_embedder or _default_embedder_factory(settings)
    else:
        make_embedder = None

    if make_embedder is not None:
        models = embedder_models or settings.embedding_models
        try:
            vectors, embedder = embed_with_failover(
                [c.text for c in chunks], [f"{c.section} {c.title}" for c in chunks], models, make_embedder
            )
        except Exception as exc:  # noqa: BLE001 - o índice lexical continua válido
            logger.warning("Índice criado sem embeddings: %s", exc)

    index = PolicyIndex(
        chunks=chunks,
        vectors=vectors,
        embedding_model=embedder.model if embedder else None,
        embedding_dims=len(vectors[0]) if vectors else None,
        source_sha256=file_sha256(pdf_path),
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if index_path is not None:
        index.save(index_path)
    return index


class Retriever:
    def __init__(
        self,
        index: PolicyIndex,
        embedder: Embedder | None = None,
        mode: str = "hybrid",
        min_semantic: float = DEFAULT_MIN_SEMANTIC,
    ):
        self.index = index
        self.embedder = embedder
        self.mode = mode
        self.min_semantic = min_semantic
        self._bm25 = BM25([document_tokens(c.title, c.text) for c in index.chunks])
        self._query_cache: dict[str, list[float]] = {}
        self.last_search_used_embeddings = False

    @property
    def semantic_enabled(self) -> bool:
        return self.mode == "hybrid" and self.embedder is not None and self.index.has_vectors

    def _query_vector(self, query: str) -> list[float] | None:
        if not self.semantic_enabled:
            return None
        if query in self._query_cache:
            return self._query_cache[query]
        try:
            vector = self.embedder.embed_query(query)
        except Exception as exc:  # noqa: BLE001 - cota, rede ou chave: segue só com BM25
            logger.warning("Embedding da pergunta falhou; usando só BM25 (%s)", str(exc)[:200])
            return None
        self._query_cache[query] = vector
        return vector

    def search(self, query: str, k: int = 4) -> list[PolicyHit]:
        query = (query or "").strip()
        self.last_search_used_embeddings = False
        if not query:
            return []

        n = len(self.index.chunks)
        lexical = self._bm25.scores(query_terms(query))
        lex_order = [i for i in sorted(range(n), key=lambda i: -lexical[i]) if lexical[i] > 0]
        lex_rank = {i: r for r, i in enumerate(lex_order)}

        vector = self._query_vector(query)
        semantic: dict[int, float] | None = None
        sem_rank: dict[int, int] = {}
        if vector is not None:
            self.last_search_used_embeddings = True
            semantic = {i: cosine(vector, self.index.vectors[i]) for i in range(n)}
            sem_order = sorted(range(n), key=lambda i: -semantic[i])
            sem_rank = {i: r for r, i in enumerate(sem_order)}

        scored: list[tuple[float, int]] = []
        for i in range(n):
            if semantic is None:
                if i in lex_rank:
                    scored.append((lexical[i], i))
                continue
            has_lex = i in lex_rank
            if not has_lex and semantic[i] < self.min_semantic:
                continue
            fused = (1 / (RRF_K + lex_rank[i] + 1) if has_lex else 0.0) + 1 / (RRF_K + sem_rank[i] + 1)
            scored.append((fused, i))
        scored.sort(key=lambda item: -item[0])

        return [
            PolicyHit(
                chunk_id=self.index.chunks[i].chunk_id,
                section=self.index.chunks[i].section,
                title=self.index.chunks[i].title,
                page=self.index.chunks[i].page,
                text=self.index.chunks[i].text,
                score=score,
                lexical_score=lexical[i],
                semantic_score=None if semantic is None else semantic[i],
            )
            for score, i in scored[:k]
        ]


def load_retriever(
    settings: Settings | None = None,
    pdf_path: Path | str = POLICIES_PDF,
    make_embedder: Callable[[str], Embedder] | None = None,
) -> Retriever:
    """Carrega o índice do disco (reconstrói se o PDF mudou, se não existe ou se faltam vetores)."""
    settings = settings or get_settings()
    hybrid = settings.rag_mode == "hybrid"
    factory = make_embedder or (_default_embedder_factory(settings) if hybrid else None)

    index: PolicyIndex | None = None
    if settings.rag_index_path.exists():
        try:
            index = PolicyIndex.load(settings.rag_index_path)
            if index.source_sha256 != file_sha256(pdf_path):
                logger.info("PDF mudou; reconstruindo o índice.")
                index = None
            elif hybrid and not index.has_vectors and factory is not None:
                logger.info("Índice sem embeddings e há chave disponível; tentando gerar.")
                index = None
        except (ValueError, KeyError, json.JSONDecodeError):
            index = None
    if index is None:
        index = build_index(pdf_path, settings.rag_index_path, make_embedder=factory, lexical_only=not hybrid)

    embedder: Embedder | None = None
    if hybrid and index.has_vectors and factory is not None:
        embedder = factory(index.embedding_model)
    return Retriever(index, embedder, mode=settings.rag_mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrói o índice das políticas da loja.")
    parser.add_argument("--lexical-only", action="store_true", help="não gera embeddings")
    parser.add_argument("--query", help="faz uma busca de teste ao final")
    parser.add_argument("-k", type=int, default=3)
    args = parser.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    index = build_index(POLICIES_PDF, settings.rag_index_path, lexical_only=args.lexical_only)
    mode = (
        f"com embeddings ({index.embedding_model}, {index.embedding_dims} dims)"
        if index.has_vectors
        else "somente lexical (BM25)"
    )
    print(f"{len(index.chunks)} chunks, índice {mode}, salvo em {settings.rag_index_path}")

    if args.query:
        retriever = load_retriever(settings)
        for hit in retriever.search(args.query, k=args.k):
            print(f"\n[{hit.section}] {hit.title}  (score {hit.score:.3f})\n{hit.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
