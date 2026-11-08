"""Catálogo: busca (com tolerância a erros de digitação), preço e disponibilidade."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from rapidfuzz import fuzz

from app.core.money import brl
from app.core.text import compact, tokens
from app.services.payments import pix_price
from app.services.promotions import best_active_promotion_rows, build_promotion_info
from app.services.schemas import CategoryInfo, ProductInfo, ProductSearchResult

MATCH_CUTOFF = 80.0
COMPACT_CUTOFF = 90.0  # casamento sem espaços ('gd 20' ~ 'gd20'); mais rígido para evitar ruído
_AVAILABILITY_ORDER = {"available": 0, "out_of_stock": 1, "coming_soon": 2, "discontinued": 3}


# --- Montagem do ProductInfo ----------------------------------------------------------
def _availability(status: str, stock: int) -> str:
    if status == "discontinued":
        return "discontinued"
    if status == "coming_soon":
        return "coming_soon"
    return "available" if stock > 0 else "out_of_stock"


def _price_summary(price: float, promo, pix: float | None) -> str:
    if promo:
        return f"{promo.summary}. O desconto do PIX não é cumulativo com promoções."
    return f"{brl(price)} (ou {brl(pix)} no PIX, com 5% de desconto)"


def _to_info(row: sqlite3.Row, promo_row: sqlite3.Row | None) -> ProductInfo:
    price = float(row["price_brl"])
    promo = build_promotion_info(promo_row, price) if promo_row else None
    pix = None if promo else pix_price(price)
    return ProductInfo(
        product_id=row["product_id"],
        name=row["name"],
        category_id=row["category_id"],
        category=row["category_name"],
        description=row["description"],
        status=row["status"],
        availability=_availability(row["status"], row["stock_quantity"]),
        stock_quantity=row["stock_quantity"],
        price_brl=price,
        promotion=promo,
        final_price_brl=promo.final_price_brl if promo else price,
        pix_price_brl=pix,
        price_summary=_price_summary(price, promo, pix),
        specs=json.loads(row["specs_json"] or "{}"),
    )


def _load_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT p.*, c.name AS category_name FROM products p "
        "JOIN categories c USING (category_id) ORDER BY p.product_id"
    ).fetchall()


def _load_infos(conn: sqlite3.Connection) -> list[tuple[sqlite3.Row, ProductInfo]]:
    promos = best_active_promotion_rows(conn)
    return [(row, _to_info(row, promos.get(row["product_id"]))) for row in _load_rows(conn)]


def get_product(conn: sqlite3.Connection, product_id: int) -> ProductInfo | None:
    for _, info in _load_infos(conn):
        if info.product_id == product_id:
            return info
    return None


# --- Categorias ------------------------------------------------------------------------
def list_categories(conn: sqlite3.Connection) -> list[CategoryInfo]:
    rows = conn.execute(
        """
        SELECT c.category_id, c.name,
               COUNT(p.product_id) AS total,
               SUM(CASE WHEN p.status = 'active' AND p.stock_quantity > 0 THEN 1 ELSE 0 END) AS available
        FROM categories c LEFT JOIN products p USING (category_id)
        GROUP BY c.category_id ORDER BY c.category_id
        """
    ).fetchall()
    return [
        CategoryInfo(
            category_id=r["category_id"],
            name=r["name"],
            total_products=r["total"],
            available_products=r["available"] or 0,
        )
        for r in rows
    ]


def resolve_categories(conn: sqlite3.Connection, text: str | None) -> list[int]:
    """Ids de categoria compatíveis com o texto ('violões', 'violao', 'sopro')."""
    query_tokens = tokens(text)
    if not query_tokens:
        return []
    matched = []
    for row in conn.execute("SELECT category_id, name FROM categories ORDER BY category_id"):
        name_tokens = tokens(row["name"])
        if all(
            max((fuzz.ratio(q, t) for t in name_tokens), default=0) >= 85 for q in query_tokens
        ):
            matched.append(row["category_id"])
    return matched


# --- Busca ------------------------------------------------------------------------------
def _best(query_token: str, candidates: list[str]) -> float:
    if len(query_token) < 3:
        return 100.0 if query_token in candidates else 0.0
    return max((fuzz.ratio(query_token, c) for c in candidates), default=0.0)


def _match_score(query: str, row: sqlite3.Row) -> tuple[float, int]:
    """Retorna (pontuação 0-100, nº de termos da busca encontrados no nome)."""
    q_tokens = tokens(query)
    if not q_tokens:
        return 0.0, 0
    name_tokens = tokens(row["name"])
    all_tokens = tokens(row["search_text"])

    in_name = min(_best(q, name_tokens) for q in q_tokens)
    in_all = 0.9 * min(_best(q, all_tokens) for q in q_tokens)
    name_hits = sum(1 for q in q_tokens if _best(q, name_tokens) >= MATCH_CUTOFF)

    q_compact = compact(query)
    compact_score = 0.0
    if len(q_compact) >= 4:
        partial = fuzz.partial_ratio(q_compact, compact(row["name"]))
        compact_score = partial if partial >= COMPACT_CUTOFF else 0.0
    return max(in_name, in_all, compact_score), name_hits


def suggest_alternatives(conn: sqlite3.Connection, product_id: int, limit: int = 3) -> list[ProductInfo]:
    """Alternativas disponíveis: mesma categoria, preço mais próximo (manual 7.3)."""
    infos = _load_infos(conn)
    target = next((i for _, i in infos if i.product_id == product_id), None)
    if target is None:
        return []
    candidates = [
        i
        for _, i in infos
        if i.product_id != product_id
        and i.category_id == target.category_id
        and i.availability == "available"
    ]
    candidates.sort(key=lambda i: abs(i.final_price_brl - target.final_price_brl))
    return candidates[:limit]


def search_products(
    conn: sqlite3.Connection,
    query: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    available_only: bool | None = None,
    on_promotion_only: bool = False,
    limit: int = 8,
) -> ProductSearchResult:
    """Busca produtos.

    - Faixa de preço considera o preço efetivo (com promoção ativa, se houver).
    - available_only: por padrão é True em listagens (sem query) e False quando o
      cliente pergunta por um produto específico, pois ele precisa saber se o item
      está esgotado, em breve ou descontinuado (manual 7.3).
    - Se o melhor resultado de uma busca por nome não estiver disponível,
      alternativas semelhantes vêm em `alternatives`.
    """
    if available_only is None:
        available_only = not (query and query.strip())

    filters: dict[str, Any] = {
        "category": category, "min_price": min_price, "max_price": max_price,
        "available_only": available_only, "on_promotion_only": on_promotion_only,
    }
    notes: list[str] = []
    entries = _load_infos(conn)

    if category:
        category_ids = resolve_categories(conn, category)
        if not category_ids:
            names = ", ".join(c.name for c in list_categories(conn))
            return ProductSearchResult(
                query=query, filters=filters, total_matches=0, products=[],
                notes=[f"Categoria '{category}' não existe no catálogo. Categorias: {names}."],
            )
        entries = [(r, i) for r, i in entries if i.category_id in category_ids]
        if not entries:
            notes.append(
                f"A categoria '{category}' existe, mas não há produtos cadastrados nela no momento."
            )

    if min_price is not None:
        entries = [(r, i) for r, i in entries if i.final_price_brl >= min_price]
    if max_price is not None:
        entries = [(r, i) for r, i in entries if i.final_price_brl <= max_price]
    if on_promotion_only:
        entries = [(r, i) for r, i in entries if i.promotion is not None]

    scores: dict[int, tuple[float, int]] = {}
    if query and query.strip():
        for row, info in entries:
            scores[info.product_id] = _match_score(query, row)
        entries = [(r, i) for r, i in entries if scores[i.product_id][0] >= MATCH_CUTOFF]

    if available_only:
        entries = [(r, i) for r, i in entries if i.availability == "available"]

    entries.sort(
        key=lambda e: (
            -round(scores.get(e[1].product_id, (0.0, 0))[0], 1),
            -scores.get(e[1].product_id, (0.0, 0))[1],
            _AVAILABILITY_ORDER[e[1].availability],
            e[1].final_price_brl,
        )
    )
    infos = [i for _, i in entries]
    top = infos[:limit]

    alternatives: list[ProductInfo] = []
    if query and top and top[0].availability != "available":
        alternatives = suggest_alternatives(conn, top[0].product_id)

    return ProductSearchResult(
        query=query,
        filters=filters,
        total_matches=len(infos),
        products=top,
        alternatives=alternatives,
        notes=notes,
    )
