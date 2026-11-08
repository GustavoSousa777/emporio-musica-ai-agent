"""Promoções (manual, seções 6 e 7.3).

Regras aplicadas:
- só vale a promoção com is_active = 1; as demais são tratadas como encerradas;
- promoções não são cumulativas: com mais de uma ativa, vale a de maior desconto;
- o preço promocional sempre vem junto do preço original e do percentual.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from app.core.money import brl, f2, q2, to_decimal
from app.services.schemas import ExpiredPromotion, PromotionInfo, PromotionStatus


def apply_discount(price: float | Decimal, percent: float | Decimal) -> float:
    final = to_decimal(price) * (Decimal(100) - to_decimal(percent)) / Decimal(100)
    return f2(final)


def _percent_text(percent: float) -> str:
    return f"{percent:g}"


def build_promotion_info(row: sqlite3.Row, list_price: float) -> PromotionInfo:
    percent = float(row["discount_percent"])
    final = apply_discount(list_price, percent)
    return PromotionInfo(
        promotion_id=row["promotion_id"],
        label=row["description"] or "Promoção",
        discount_percent=percent,
        original_price_brl=f2(list_price),
        final_price_brl=final,
        savings_brl=f2(q2(list_price) - q2(final)),
        summary=f"De {brl(list_price)} por {brl(final)} ({_percent_text(percent)}% de desconto)",
    )


def best_active_promotion_rows(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """Uma promoção ativa por produto: a de maior desconto (empate: menor id)."""
    best: dict[int, sqlite3.Row] = {}
    rows = conn.execute(
        "SELECT * FROM promotions WHERE is_active = 1 "
        "ORDER BY discount_percent DESC, promotion_id ASC"
    )
    for row in rows:
        best.setdefault(row["product_id"], row)
    return best


def get_promotion_status(conn: sqlite3.Connection, product_id: int) -> PromotionStatus | None:
    """Situação das promoções de um produto, incluindo as já encerradas."""
    product = conn.execute(
        "SELECT product_id, name, price_brl FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    if product is None:
        return None

    active_row = best_active_promotion_rows(conn).get(product_id)
    active = build_promotion_info(active_row, product["price_brl"]) if active_row else None
    expired = [
        ExpiredPromotion(
            promotion_id=r["promotion_id"],
            label=r["description"] or "Promoção",
            discount_percent=float(r["discount_percent"]),
        )
        for r in conn.execute(
            "SELECT * FROM promotions WHERE product_id = ? AND is_active = 0 ORDER BY promotion_id",
            (product_id,),
        )
    ]

    if active:
        message = f"Promoção ativa: {active.summary}."
    elif expired:
        message = (
            "Não há promoção ativa para este produto; as anteriores já foram encerradas. "
            f"O preço atual é {brl(product['price_brl'])}. Não prometa descontos que não estão vigentes."
        )
    else:
        message = f"Este produto não tem promoção. O preço atual é {brl(product['price_brl'])}."

    return PromotionStatus(
        product_id=product["product_id"],
        product_name=product["name"],
        current_price_brl=f2(product["price_brl"]),
        active=active,
        expired=expired,
        message=message,
    )
