"""Relógio único do sistema.

Toda regra que depende de "hoje" (horário de funcionamento, prazo de devolução)
passa por get_now(). Isso permite fixar a data em testes e em demonstrações
via parâmetro ou variável NOW_OVERRIDE.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def get_now(override: datetime | str | None = None) -> datetime:
    """Retorna o instante atual com fuso (America/Campo_Grande por padrão)."""
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)

    value = override if override is not None else settings.now_override
    if value is None:
        return datetime.now(tz)
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)
