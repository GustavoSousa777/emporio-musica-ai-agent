from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

from app.core.money import brl, q2, to_decimal
from app.core.rules import (
    ORDER_STATUSES,
    PRODUCT_STATUSES,
    TRACKING_CODE_PATTERN,
    min_installment_value,
)
from app.database.issues import IssueLog


def _ids(rows: list[sqlite3.Row], key: str) -> str:
    return ", ".join(str(r[key]) for r in rows)


def run_validations(conn: sqlite3.Connection, log: IssueLog) -> None:
    _check_foreign_keys(conn, log)
    _check_domains(conn, log)
    _check_products(conn, log)
    _check_promotions(conn, log)
    _check_customers(conn, log)
    _check_orders(conn, log)


def _check_foreign_keys(conn: sqlite3.Connection, log: IssueLog) -> None:
    for row in conn.execute("PRAGMA foreign_key_check"):
        log.add(
            "FK_ORPHAN",
            "error",
            row["table"],
            row["rowid"],
            f"Chave estrangeira inválida em {row['table']} (rowid {row['rowid']}) -> {row['parent']}",
        )


def _check_domains(conn: sqlite3.Connection, log: IssueLog) -> None:
    for r in conn.execute("SELECT product_id, status FROM products"):
        if r["status"] not in PRODUCT_STATUSES:
            log.add("UNKNOWN_PRODUCT_STATUS", "error", "product", r["product_id"], f"status desconhecido: {r['status']!r}")
    for r in conn.execute("SELECT order_id, status FROM orders"):
        if r["status"] not in ORDER_STATUSES:
            log.add("UNKNOWN_ORDER_STATUS", "error", "order", r["order_id"], f"status desconhecido: {r['status']!r}")
    for r in conn.execute("SELECT product_id FROM products WHERE stock_quantity < 0"):
        log.add("NEGATIVE_STOCK", "error", "product", r["product_id"], "estoque negativo")


def _check_products(conn: sqlite3.Connection, log: IssueLog) -> None:
    for r in conn.execute(
        "SELECT product_id, name, stock_quantity FROM products "
        "WHERE status = 'active' AND stock_quantity = 0"
    ):
        log.add(
            "ACTIVE_WITHOUT_STOCK",
            "warning",
            "product",
            r["product_id"],
            f"{r['name']} está 'active' mas com estoque 0. O agente deve tratá-lo como indisponível.",
        )

    for r in conn.execute(
        "SELECT category_id, name FROM categories "
        "WHERE category_id NOT IN (SELECT category_id FROM products) ORDER BY category_id"
    ):
        log.add(
            "EMPTY_CATEGORY",
            "info",
            "category",
            r["category_id"],
            f"Categoria '{r['name']}' não tem nenhum produto no catálogo "
            "(o manual cita esses instrumentos, mas a base não tem itens).",
        )


def _check_promotions(conn: sqlite3.Connection, log: IssueLog) -> None:
    for r in conn.execute(
        """
        SELECT pr.promotion_id, p.product_id, p.name, p.status, p.stock_quantity
        FROM promotions pr JOIN products p USING (product_id)
        WHERE pr.is_active = 1 AND (p.status != 'active' OR p.stock_quantity = 0)
        """
    ):
        log.add(
            "ACTIVE_PROMO_ON_UNAVAILABLE_PRODUCT",
            "warning",
            "promotion",
            r["promotion_id"],
            f"Promoção ativa em produto indisponível: {r['name']} ({r['status']}, estoque {r['stock_quantity']}).",
        )

    for r in conn.execute(
        """
        SELECT product_id, COUNT(*) AS n, GROUP_CONCAT(promotion_id) AS ids
        FROM promotions WHERE is_active = 1 GROUP BY product_id HAVING n > 1
        """
    ):
        log.add(
            "MULTIPLE_ACTIVE_PROMOTIONS",
            "warning",
            "product",
            r["product_id"],
            f"Mais de uma promoção ativa (ids {r['ids']}). Promoções não são cumulativas (manual 6.2).",
        )


def _check_customers(conn: sqlite3.Connection, log: IssueLog) -> None:
    for r in conn.execute(
        """
        SELECT email_norm, GROUP_CONCAT(customer_id) AS ids, GROUP_CONCAT(name, ' | ') AS names
        FROM customers WHERE email_norm IS NOT NULL
        GROUP BY email_norm HAVING COUNT(*) > 1
        """
    ):
        log.add(
            "DUPLICATE_EMAIL",
            "warning",
            "customer",
            r["ids"],
            f"E-mail repetido em clientes distintos ({r['names']}): possível cliente duplicado.",
        )


def _check_orders(conn: sqlite3.Connection, log: IssueLog) -> None:
    tracking_re = re.compile(TRACKING_CODE_PATTERN)

    # Soma dos itens (preço atual) vs total do pedido
    for r in conn.execute(
        """
        SELECT o.order_id, o.total_brl, SUM(oi.quantity * p.price_brl) AS items_total
        FROM orders o
        JOIN order_items oi USING (order_id)
        JOIN products p USING (product_id)
        GROUP BY o.order_id
        """
    ):
        diff = q2(to_decimal(r["total_brl"]) - to_decimal(r["items_total"]))
        if abs(diff) > to_decimal("0.01"):
            log.add(
                "ORDER_TOTAL_MISMATCH",
                "warning",
                "order",
                r["order_id"],
                f"Total do pedido ({brl(r['total_brl'])}) difere da soma dos itens a preço atual "
                f"({brl(r['items_total'])}); diferença de {brl(diff)}. O agente usa o total do pedido.",
            )

    # Itens de produtos que não estão ativos
    rows = conn.execute(
        """
        SELECT oi.order_id, p.product_id, p.name, p.status
        FROM order_items oi JOIN products p USING (product_id)
        WHERE p.status != 'active' ORDER BY oi.order_id
        """
    ).fetchall()
    for r in rows:
        log.add(
            "ORDERED_UNAVAILABLE_PRODUCT",
            "warning",
            "order",
            r["order_id"],
            f"Pedido contém '{r['name']}' (produto {r['product_id']}) com status '{r['status']}'.",
        )

    by_order: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM orders ORDER BY order_id"):
        by_order[r["order_id"]] = r

    for o in by_order.values():
        oid, status, code = o["order_id"], o["status"], o["tracking_code"]
        if code and not tracking_re.match(code):
            log.add("TRACKING_FORMAT", "warning", "order", oid, f"Código de rastreio fora do padrão: {code}")
        if status in ("shipped", "delivered") and not code:
            log.add("MISSING_TRACKING", "warning", "order", oid, f"Pedido '{status}' sem código de rastreio.")
        if status in ("pending", "confirmed", "cancelled") and code:
            log.add("UNEXPECTED_TRACKING", "warning", "order", oid, f"Pedido '{status}' com código de rastreio.")
        if o["estimated_delivery"] and o["order_date"] and o["estimated_delivery"] < o["order_date"]:
            log.add("DELIVERY_BEFORE_ORDER", "warning", "order", oid, "Entrega prevista anterior à data do pedido.")
        if status == "delivered" and not o["estimated_delivery"]:
            log.add("DELIVERED_WITHOUT_DATE", "warning", "order", oid, "Pedido entregue sem data de entrega.")

        # Parcela mínima do manual (3.1)
        n = o["installments"]
        if o["payment_type"] == "credit" and n > 1:
            parcel = to_decimal(o["total_brl"]) / n
            minimum = min_installment_value(n)
            if parcel < minimum:
                log.add(
                    "INSTALLMENT_BELOW_POLICY",
                    "warning",
                    "order",
                    oid,
                    f"Parcelado em {n}x de {brl(parcel)}, abaixo da parcela mínima de {brl(minimum)} (manual 3.1).",
                )
