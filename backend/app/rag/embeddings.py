"""Embeddings via Gemini, com suporte aos dois formatos de modelo.

- gemini-embedding-001: usa `task_type` (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY).
- gemini-embedding-2: não aceita `task_type`; a tarefa vai no texto
  ("title: ... | text: ..." para documentos e "task: search result | query: ..." para
  perguntas) e cada texto precisa estar em um `Content` próprio, senão a API devolve
  UM embedding agregado para todos.

Os vetores são normalizados (norma L2 = 1), então o produto escalar é o cosseno.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Callable, Protocol

from app.core.gemini_failover import LLMUnavailableError, ModelPool, classify_error

logger = logging.getLogger(__name__)

TIMEOUT_MS = 25_000


class Embedder(Protocol):
    model: str
    dims: int | None

    def embed_documents(self, texts: list[str], titles: list[str] | None = None) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values] if norm else list(values)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def is_v2(model: str) -> bool:
    return model.startswith("gemini-embedding-2")


def make_client(api_key: str):
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


class GeminiEmbedder:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        dims: int | None = 768,
        batch_size: int = 10,
        pause_seconds: float = 2.0,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if client is None and not api_key:
            raise ValueError("GEMINI_API_KEY não configurada.")
        self.model = model
        self.dims = dims
        self.batch_size = batch_size
        self.pause_seconds = pause_seconds
        self._client = client if client is not None else make_client(api_key)
        self._sleep = sleep

    def _doc_text(self, text: str, title: str | None) -> str:
        return f"title: {title or 'none'} | text: {text}" if is_v2(self.model) else text

    def _query_text(self, text: str) -> str:
        return f"task: search result | query: {text}" if is_v2(self.model) else text

    def _call(self, texts: list[str], task_type: str):
        from google.genai import types

        if is_v2(self.model):
            contents = [types.Content(parts=[types.Part.from_text(text=t)]) for t in texts]
            config = types.EmbedContentConfig(output_dimensionality=self.dims) if self.dims else None
        else:
            contents = texts
            config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dims)
        last_error: BaseException | None = None
        for attempt in (1, 2):
            try:
                return self._client.models.embed_content(model=self.model, contents=contents, config=config)
            except Exception as exc:  # noqa: BLE001 - classificado abaixo
                last_error = exc
                if attempt == 1 and classify_error(exc).retry_same_model:
                    self._sleep(2.0)
                    continue
                raise
        raise last_error  # pragma: no cover

    def embed_documents(self, texts: list[str], titles: list[str] | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            if start > 0 and self.pause_seconds:
                self._sleep(self.pause_seconds)
            batch = texts[start : start + self.batch_size]
            batch_titles = (titles or [None] * len(texts))[start : start + self.batch_size]
            formatted = [self._doc_text(t, title) for t, title in zip(batch, batch_titles)]
            response = self._call(formatted, "RETRIEVAL_DOCUMENT")
            vectors += [normalize_vector(list(e.values)) for e in response.embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError(f"A API devolveu {len(vectors)} vetores para {len(texts)} textos.")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        response = self._call([self._query_text(text)], "RETRIEVAL_QUERY")
        return normalize_vector(list(response.embeddings[0].values))


def embed_with_failover(
    texts: list[str],
    titles: list[str] | None,
    models: list[str] | tuple[str, ...],
    make_embedder: Callable[[str], Embedder],
    pool: ModelPool | None = None,
) -> tuple[list[list[float]], Embedder]:
    """Vetoriza todos os textos com UM único modelo (vetores de modelos diferentes não se comparam).

    Se um modelo falhar no meio (ex.: cota), descarta o progresso e recomeça no próximo.
    """
    pool = pool or ModelPool(models)
    last_error: BaseException | None = None
    for model in pool.candidates():
        embedder = make_embedder(model)
        try:
            return embedder.embed_documents(texts, titles), embedder
        except Exception as exc:  # noqa: BLE001
            info = classify_error(exc)
            if not info.switch_model:
                raise
            seconds = pool.block(model, info)
            logger.warning("Embedding %s falhou (%s); bloqueado por %.0fs", model, info.text[:200], seconds)
            last_error = exc
    raise LLMUnavailableError(
        f"Nenhum modelo de embedding respondeu: {last_error}",
        wait_seconds=pool.wait_seconds(),
        daily_quota=pool.all_daily(),
    )
