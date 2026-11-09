"""Busca lexical (BM25) em português, sem dependências externas.

Funciona sem chave de API e sem rede, e serve de base para a busca híbrida.
O vocabulário do cliente ("devolver", "estragou", "quantas vezes") é aproximado do
vocabulário do manual ("arrependimento", "defeito", "parcelamento") por uma lista
curta de expansões, com peso menor que os termos originais.
"""
from __future__ import annotations

import math
from collections import Counter

from app.core.text import STOPWORDS, normalize, stem

PREFIX_LEN = 4
EXPANSION_WEIGHT = 0.6
TITLE_BOOST = 2  # o título conta duas vezes no documento

# palavra do cliente -> termos do manual
_RAW_EXPANSIONS = {
    "devolver": "devolucao arrependimento reembolso",
    "devolucao": "arrependimento reembolso",
    "desistir": "arrependimento devolucao",
    "desisti": "arrependimento devolucao",
    "arrependi": "arrependimento devolucao reembolso",
    "cancelar": "devolucao arrependimento",
    "reembolso": "devolucao arrependimento",
    "estragou": "defeito fabricacao garantia",
    "quebrou": "defeito fabricacao garantia",
    "pifou": "defeito fabricacao garantia",
    "defeito": "fabricacao garantia troca",
    "parar": "defeito garantia",
    "parcelar": "parcelamento credito cartao",
    "parcela": "parcelamento credito cartao",
    "vezes": "parcelamento credito",
    "cartao": "credito debito pagamento",
    "pagar": "pagamento formas",
    "pagamento": "formas",
    "entrega": "frete prazo entregas",
    "entregam": "frete entregas",
    "enviar": "frete entregas",
    "envio": "frete entregas",
    "mandar": "frete entregas",
    "rastrear": "rastreamento codigo",
    "rastreio": "rastreamento codigo",
    "horario": "funcionamento",
    "abre": "horario funcionamento",
    "fecha": "horario funcionamento",
    "aberto": "horario funcionamento",
    "domingo": "horario funcionamento fechado",
    "exclusao": "dados lgpd",
    "excluir": "exclusao dados lgpd",
    "apagar": "exclusao dados lgpd",
    "privacidade": "dados lgpd",
    "desconto": "promocao",
    "promocao": "desconto",
    "endereco": "empresa dados",
    "telefone": "whatsapp contato",
    "contato": "telefone whatsapp email",
    "acessorios": "exclusivamente escopo instrumentos",
    "cordas": "acessorios exclusivamente",
    "palhetas": "acessorios exclusivamente",
    "cabos": "acessorios exclusivamente",
    "pedais": "acessorios exclusivamente",
    "amplificador": "acessorios exclusivamente",
    "reclamacao": "reclamar retorno",
    "reclamar": "reclamacao retorno",
}


def lex_stem(token: str) -> str:
    """Radical agressivo (prefixo de 4 letras) para casar 'pagar' com 'pagamento'."""
    token = stem(token)
    return token[:PREFIX_LEN] if len(token) > PREFIX_LEN else token


def lex_tokens(text: str | None) -> list[str]:
    return [lex_stem(t) for t in normalize(text).split() if t not in STOPWORDS]


EXPANSIONS: dict[str, list[str]] = {
    lex_tokens(key)[0]: lex_tokens(value) for key, value in _RAW_EXPANSIONS.items()
}


def query_terms(query: str) -> dict[str, float]:
    """Termos da busca com peso: originais 1.0, expansões 0.6."""
    terms: dict[str, float] = {}
    original = lex_tokens(query)
    for token in original:
        terms[token] = 1.0
    for token in original:
        for extra in EXPANSIONS.get(token, []):
            terms.setdefault(extra, EXPANSION_WEIGHT)
    return terms


def document_tokens(title: str, text: str) -> list[str]:
    return lex_tokens(title) * TITLE_BOOST + lex_tokens(text)


class BM25:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.documents = documents
        self.counters = [Counter(doc) for doc in documents]
        self.lengths = [len(doc) for doc in documents]
        self.avg_length = (sum(self.lengths) / len(documents)) if documents else 0.0
        df: Counter[str] = Counter()
        for counter in self.counters:
            df.update(counter.keys())
        n = len(documents)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, terms: dict[str, float]) -> list[float]:
        result = []
        for counter, length in zip(self.counters, self.lengths):
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_length) if self.avg_length else self.k1
            score = 0.0
            for term, weight in terms.items():
                tf = counter.get(term, 0)
                if tf:
                    score += weight * self.idf.get(term, 0.0) * tf * (self.k1 + 1) / (tf + norm)
            result.append(score)
        return result
