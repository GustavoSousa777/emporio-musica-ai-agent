"""Conexão com o SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import get_settings


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else get_settings().db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_database(db_path: Path | str | None = None) -> Path:
    """Garante que o banco exista; se não existir, executa o seed."""
    path = Path(db_path) if db_path else get_settings().db_path
    if not path.exists():
        from app.database.seed import seed_database

        seed_database(db_path=path)
    return path
