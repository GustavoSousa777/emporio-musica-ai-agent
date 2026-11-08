"""Aritmética monetária com Decimal (evita erros de ponto flutuante)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q2(value: float | int | str | Decimal) -> Decimal:
    return to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def f2(value: float | int | str | Decimal) -> float:
    return float(q2(value))


def brl(value: float | int | str | Decimal) -> str:
    """Formata como moeda brasileira: R$ 1.234,56."""
    text = f"{q2(value):,.2f}"
    return "R$ " + text.replace(",", "_").replace(".", ",").replace("_", ".")
