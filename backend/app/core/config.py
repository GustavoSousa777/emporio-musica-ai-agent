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

load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    db_path: Path
    timezone: str
    now_override: str | None
    gemini_api_key: str | None
    gemini_model: str | None


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def get_settings() -> Settings:
    """Lê o ambiente a cada chamada (permite sobrescrever em testes)."""
    db_path = Path(os.environ.get("DB_PATH") or "data/emporio.db")
    if not db_path.is_absolute():
        db_path = BACKEND_DIR / db_path
    return Settings(
        db_path=db_path,
        timezone=os.environ.get("TIMEZONE") or "America/Campo_Grande",
        now_override=_blank_to_none(os.environ.get("NOW_OVERRIDE")),
        gemini_api_key=_blank_to_none(os.environ.get("GEMINI_API_KEY")),
        gemini_model=_blank_to_none(os.environ.get("GEMINI_MODEL")),
    )
