"""Configuração via variáveis de ambiente (.env em backend/)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
RAW_DATA_DIR = BACKEND_DIR / "data" / "raw"
POLICIES_DIR = BACKEND_DIR / "data" / "policies"
POLICIES_PDF = POLICIES_DIR / "politicas_da_loja.pdf"

load_dotenv(BACKEND_DIR / ".env")

# Nomes de modelo mudam com frequência. Se algum não existir ou estourar a cota, o failover
# (app/core/gemini_failover.py) bloqueia o modelo e passa para o próximo da lista.
# Ajuste pelo .env: GEMINI_MODEL, GEMINI_FALLBACK_MODELS, GEMINI_EMBEDDING_MODELS.
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_FALLBACK_MODELS = "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
DEFAULT_EMBEDDING_MODELS = "gemini-embedding-001,gemini-embedding-2"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    conversations_db_path: Path
    rag_index_path: Path
    timezone: str
    now_override: str | None
    gemini_api_key: str | None
    gemini_models: tuple[str, ...]  # principal + reservas, em ordem de preferência
    gemini_thinking_level: str | None
    embedding_models: tuple[str, ...]
    embedding_dims: int
    rag_mode: str  # "hybrid" (BM25 + embeddings) ou "lexical" (só BM25)


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _path(env_name: str, default: str) -> Path:
    path = Path(os.environ.get(env_name) or default)
    return path if path.is_absolute() else BACKEND_DIR / path


def get_settings() -> Settings:
    """Lê o ambiente a cada chamada (permite sobrescrever em testes)."""
    primary = _blank_to_none(os.environ.get("GEMINI_MODEL")) or DEFAULT_MODEL
    fallbacks = _csv(os.environ.get("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS))
    models = tuple(dict.fromkeys([primary, *fallbacks]))
    embedding_models = tuple(
        dict.fromkeys(_csv(os.environ.get("GEMINI_EMBEDDING_MODELS") or DEFAULT_EMBEDDING_MODELS))
    )
    rag_mode = (os.environ.get("RAG_MODE") or "hybrid").strip().lower()
    return Settings(
        db_path=_path("DB_PATH", "data/emporio.db"),
        conversations_db_path=_path("CONVERSATIONS_DB_PATH", "data/conversations.db"),
        rag_index_path=_path("RAG_INDEX_PATH", "data/index/policies_index.json"),
        timezone=os.environ.get("TIMEZONE") or "America/Campo_Grande",
        now_override=_blank_to_none(os.environ.get("NOW_OVERRIDE")),
        gemini_api_key=_blank_to_none(os.environ.get("GEMINI_API_KEY"))
        or _blank_to_none(os.environ.get("GOOGLE_API_KEY")),
        gemini_models=models,
        gemini_thinking_level=_blank_to_none(os.environ.get("GEMINI_THINKING_LEVEL")),
        embedding_models=embedding_models,
        embedding_dims=int(os.environ.get("GEMINI_EMBEDDING_DIMS") or 768),
        rag_mode=rag_mode if rag_mode in ("hybrid", "lexical") else "hybrid",
    )
