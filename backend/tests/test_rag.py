"""RAG das políticas: extração do PDF, chunking por seção, índice em arquivo e busca."""
from __future__ import annotations

import math

import pytest

from app.core.config import POLICIES_PDF
from app.rag.embeddings import normalize_vector
from app.rag.ingestion import chunk_policy_pdf
from app.rag.lexical import lex_tokens, query_terms
from app.rag.retriever import PolicyIndex, Retriever, build_index, load_retriever


# --- ingestão -------------------------------------------------------------------------
def test_chunking_cobre_as_secoes_do_manual(lexical_index):
    ids = {c.chunk_id for c in lexical_index.chunks}
    assert {"s2", "s3", "s3.1", "s4.1", "s4.2", "s4.4", "s5.1", "s5.2", "s5.3", "s6.2", "s7.3", "s8.1", "s9"} <= ids
    assert len(lexical_index.chunks) >= 20


def test_chunks_sem_cabecalho_e_rodape_de_pagina(lexical_index):
    for chunk in lexical_index.chunks:
        assert "Página " not in chunk.text
        assert "Manual de Políticas e Procedimentos" not in chunk.text
        assert chunk.text.strip()


def test_subsecao_carrega_o_contexto_da_secao_mae(lexical_index):
    chunk = next(c for c in lexical_index.chunks if c.chunk_id == "s4.1")
    assert chunk.parent_section == "4"
    assert "Política de Trocas e Devoluções" in chunk.text
    assert "7 (sete) dias" in chunk.text


def test_tabela_de_pagamento_fica_no_mesmo_chunk(lexical_index):
    chunk = next(c for c in lexical_index.chunks if c.chunk_id == "s3")
    assert "PIX" in chunk.text and "Cartão de Crédito" in chunk.text and "R$ 100,00" in chunk.text


def test_capa_nao_vira_chunk(lexical_index):
    assert not any("Uso restrito" in c.text for c in lexical_index.chunks)


# --- busca lexical ---------------------------------------------------------------------
PERGUNTAS = [
    ("Posso devolver um produto que comprei online?", "4.1"),
    ("Qual o prazo para trocar por defeito?", "4.2"),
    ("Quantas vezes posso parcelar no cartão?", "3.1"),
    ("O desconto do PIX vale em produto em promoção?", "6.2"),
    ("Quanto custa o frete para Campo Grande?", "5.1"),
    ("Vocês entregam em outras cidades? Quais transportadoras?", "5.2"),
    ("A garantia cobre dano por queda?", "8.3"),
    ("Qual a garantia dos instrumentos?", "8.1"),
    ("Posso trocar a cor do violão?", "4.3"),
    ("Como solicito exclusão dos meus dados?", "9"),
    ("Qual o horário de funcionamento?", "2"),
    ("Como é o código de rastreamento?", "5.3"),
    ("Posso devolver uma boquilha?", "4.4"),
    ("Em quanto tempo retornam uma reclamação?", "7.3"),
    ("Qual o endereço da loja?", "1.2"),
    ("Vocês vendem cordas e palhetas?", "1"),
    ("Meu violão estragou, o que faço?", "4.2"),
    ("Posso pagar com dois cartões?", "3.1"),
]


@pytest.mark.parametrize("pergunta,secao", PERGUNTAS)
def test_pergunta_conhecida_traz_a_secao_certa_no_top3(retriever, pergunta, secao):
    sections = [h.section for h in retriever.search(pergunta, k=3)]
    assert secao in sections, f"{pergunta!r} -> {sections}"


@pytest.mark.parametrize("pergunta", ["Qual a capital da França?", "Quem ganhou a copa do mundo?", "   ", ""])
def test_pergunta_fora_do_escopo_nao_traz_trechos(retriever, pergunta):
    assert retriever.search(pergunta) == []


def test_k_limita_resultados_e_ordena_por_score(retriever):
    hits = retriever.search("como pagar e parcelar", k=2)
    assert len(hits) <= 2
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_expansao_aproxima_vocabulario_do_cliente_do_manual():
    assert set(lex_tokens("arrependimento")) <= set(query_terms("posso devolver?"))
    assert query_terms("devolver")[lex_tokens("devolver")[0]] == 1.0


# --- índice em arquivo ------------------------------------------------------------------
def test_indice_lexical_salva_e_carrega(lexical_index, tmp_path):
    path = tmp_path / "index.json"
    lexical_index.save(path)
    loaded = PolicyIndex.load(path)
    assert not loaded.has_vectors
    assert [c.chunk_id for c in loaded.chunks] == [c.chunk_id for c in lexical_index.chunks]
    assert loaded.source_sha256 == lexical_index.source_sha256


class FakeEmbedder:
    """Embedder determinístico: bag-of-words em 64 dimensões (sem rede)."""

    dims = 64

    def __init__(self, model="fake-embedding", fail=False):
        self.model = model
        self.fail = fail
        self.query_calls = 0

    def _vec(self, text):
        vec = [0.0] * self.dims
        for token in lex_tokens(text):
            vec[hash(token) % self.dims] += 1.0
        return normalize_vector(vec)

    def embed_documents(self, texts, titles=None):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        self.query_calls += 1
        if self.fail:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return self._vec(text)


def test_indice_com_vetores_salva_e_carrega(tmp_path):
    index = build_index(make_embedder=lambda model: FakeEmbedder(model), embedder_models=["fake-embedding"])
    assert index.has_vectors and index.embedding_model == "fake-embedding"
    path = tmp_path / "index.json"
    index.save(path)
    loaded = PolicyIndex.load(path)
    assert loaded.has_vectors and len(loaded.vectors) == len(loaded.chunks)
    assert math.isclose(sum(x * x for x in loaded.vectors[0]), 1.0, rel_tol=1e-3)


def test_busca_hibrida_usa_embeddings_e_acha_a_secao(tmp_path):
    embedder = FakeEmbedder()
    index = build_index(make_embedder=lambda model: embedder)
    retriever = Retriever(index, embedder, mode="hybrid")
    hits = retriever.search("Posso devolver um produto que comprei online?", k=3)
    assert retriever.last_search_used_embeddings
    assert "4.1" in [h.section for h in hits]
    assert all(h.semantic_score is not None for h in hits)


def test_busca_hibrida_cai_para_bm25_se_o_embedding_falhar():
    embedder = FakeEmbedder()
    index = build_index(make_embedder=lambda model: embedder)
    embedder.fail = True
    retriever = Retriever(index, embedder, mode="hybrid")
    hits = retriever.search("Qual o prazo para trocar por defeito?", k=3)
    assert not retriever.last_search_used_embeddings
    assert "4.2" in [h.section for h in hits]


def test_embedding_da_pergunta_e_cacheado():
    embedder = FakeEmbedder()
    retriever = Retriever(build_index(make_embedder=lambda model: embedder), embedder, "hybrid")
    retriever.search("frete para Campo Grande")
    retriever.search("frete para Campo Grande")
    assert embedder.query_calls == 1


def test_modo_lexical_ignora_embedder():
    embedder = FakeEmbedder()
    retriever = Retriever(build_index(make_embedder=lambda model: embedder), embedder, "lexical")
    retriever.search("frete")
    assert embedder.query_calls == 0


def test_indice_sem_vetores_com_embedder_funciona_so_com_bm25(lexical_index):
    retriever = Retriever(lexical_index, FakeEmbedder(), "hybrid")
    assert not retriever.semantic_enabled
    assert retriever.search("horário de funcionamento")[0].section == "2"


def test_build_index_sobrevive_a_falha_total_de_embeddings():
    class Broken(FakeEmbedder):
        def embed_documents(self, texts, titles=None):
            raise RuntimeError("sem rede")

    index = build_index(make_embedder=lambda model: Broken(model))
    assert not index.has_vectors and index.chunks


# --- load_retriever -----------------------------------------------------------------------
@pytest.fixture()
def lexical_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RAG_INDEX_PATH", str(tmp_path / "idx" / "policies.json"))
    monkeypatch.setenv("RAG_MODE", "lexical")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    return tmp_path / "idx" / "policies.json"


def test_load_retriever_cria_o_arquivo_de_indice(lexical_env):
    retriever = load_retriever()
    assert lexical_env.exists()
    assert retriever.search("prazo de entrega em Campo Grande")[0].section == "5.1"


def test_load_retriever_reconstroi_quando_o_pdf_muda(lexical_env):
    load_retriever()
    import json

    data = json.loads(lexical_env.read_text(encoding="utf-8"))
    data["source_sha256"] = "outro-hash"
    lexical_env.write_text(json.dumps(data), encoding="utf-8")
    load_retriever()
    assert json.loads(lexical_env.read_text(encoding="utf-8"))["source_sha256"] != "outro-hash"


def test_load_retriever_recupera_de_indice_corrompido(lexical_env):
    lexical_env.parent.mkdir(parents=True)
    lexical_env.write_text("{não é json", encoding="utf-8")
    assert load_retriever().search("garantia legal")


def test_extracao_e_deterministica():
    a = [c.text for c in chunk_policy_pdf(POLICIES_PDF)]
    b = [c.text for c in chunk_policy_pdf(POLICIES_PDF)]
    assert a == b
