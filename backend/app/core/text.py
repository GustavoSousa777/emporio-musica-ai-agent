"""Normalização de texto para busca (sem acento, minúsculas, plural simples)."""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    {
        "a", "o", "e", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
        "um", "uma", "uns", "umas", "com", "sem", "para", "por", "ate", "que", "qual",
        "quais", "tem", "ter", "voce", "voces", "eu", "me", "meu", "minha", "opcao",
        "opcoes", "disponivel", "disponiveis", "preco", "quanto", "custa",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str | None) -> str:
    """minúsculas, sem acentos, só letras/dígitos separados por espaço."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", without_marks.casefold()).strip()


def compact(text: str | None) -> str:
    """Versão sem espaços, para casar 'gd 20' com 'gd20'."""
    return normalize(text).replace(" ", "")


def stem(token: str) -> str:
    """Stemming mínimo de plural em português (violões -> violao, guitarras -> guitarra)."""
    if len(token) > 4 and token.endswith(("oes", "aes")):
        return token[:-3] + "ao"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(text: str | None, drop_stopwords: bool = True) -> list[str]:
    result = []
    for tok in normalize(text).split():
        if drop_stopwords and tok in STOPWORDS:
            continue
        result.append(stem(tok))
    return result


def digits_only(text: str | None) -> str:
    return re.sub(r"\D+", "", text or "")
