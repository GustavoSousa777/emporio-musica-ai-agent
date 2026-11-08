"""Consulta de pedidos com verificação de identidade.

Privacidade (LGPD, manual seção 9): dados de um pedido só são devolvidos quando o
cliente informa o e-mail e/ou o telefone cadastrados no pedido. "Pedido
inexistente" e "dados não conferem" geram a mesma resposta, para não revelar quais
números de pedido existem.
"""
from __future__ import annotations

import sqlite3

from app.core.money import f2
from app.core.text import digits_only
from app.services.schemas import OrderInfo, OrderItemInfo, OrderLookup

STATUS_LABELS = {
    "pending": "Pendente",
    "confirmed": "Confirmado",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

# ASSUMPTION: o manual não descreve cada status; estas explicações são a leitura
# natural dos nomes e podem ser ajustadas sem mexer no restante.
STATUS_EXPLANATIONS = {
    "pending": "Pedido registrado, aguardando confirmação do pagamento.",
    "confirmed": "Pagamento confirmado; o pedido ainda não foi despachado.",
    "shipped": "Pedido despachado e a caminho do cliente.",
    "delivered": "Pedido entregue.",
    "cancelled": "Pedido cancelado.",
}

PAYMENT_LABELS = {
    "pix": "PIX",
    "debit": "Cartão de débito",
    "boleto": "Boleto bancário",
}

NOT_VERIFIED_MESSAGE = (
    "Não consegui localizar um pedido com esses dados. Confira o número do pedido e o "
    "e-mail ou telefone usados na compra."
)
VERIFICATION_REQUIRED_MESSAGE = (
    "Para consultar um pedido, preciso do número do pedido e do e-mail ou telefone "
    "cadastrados na compra."
)


def _payment_label(payment_type: str, installments: int) -> str:
    if payment_type == "credit":
        return "Cartão de crédito à vista" if installments == 1 else f"Cartão de crédito em {installments}x"
    return PAYMENT_LABELS.get(payment_type, payment_type)


def _phone_matches(stored_digits: str | None, provided: str) -> bool:
    digits = digits_only(provided)[-11:]
    return bool(stored_digits) and len(digits) >= 8 and stored_digits.endswith(digits)


def _email_matches(stored_norm: str | None, provided: str) -> bool:
    return bool(stored_norm) and stored_norm == provided.strip().lower()


def lookup_order(
    conn: sqlite3.Connection,
    order_id: int,
    email: str | None = None,
    phone: str | None = None,
) -> OrderLookup:
    """Busca um pedido. Todo dado de verificação informado precisa conferir."""
    email = (email or "").strip() or None
    phone = (phone or "").strip() or None
    if not email and not phone:
        return OrderLookup(status="verification_required", message=VERIFICATION_REQUIRED_MESSAGE)

    row = conn.execute(
        """
        SELECT o.*, c.name AS customer_name, c.email_norm, c.phone_digits
        FROM orders o JOIN customers c USING (customer_id)
        WHERE o.order_id = ?
        """,
        (order_id,),
    ).fetchone()

    verified = row is not None
    if verified and email:
        verified = _email_matches(row["email_norm"], email)
    if verified and phone:
        verified = _phone_matches(row["phone_digits"], phone)
    if not verified:
        return OrderLookup(status="not_verified", message=NOT_VERIFIED_MESSAGE)

    items = [
        OrderItemInfo(product_id=r["product_id"], name=r["name"], quantity=r["quantity"])
        for r in conn.execute(
            """
            SELECT oi.product_id, p.name, oi.quantity
            FROM order_items oi JOIN products p USING (product_id)
            WHERE oi.order_id = ? ORDER BY oi.item_id
            """,
            (order_id,),
        )
    ]
    order = OrderInfo(
        order_id=row["order_id"],
        customer_first_name=row["customer_name"].split()[0],
        order_date=row["order_date"],
        status=row["status"],
        status_label=STATUS_LABELS.get(row["status"], row["status"]),
        status_explanation=STATUS_EXPLANATIONS.get(row["status"], ""),
        items=items,
        total_brl=f2(row["total_brl"]),
        payment_method_label=_payment_label(row["payment_type"], row["installments"]),
        tracking_code=row["tracking_code"],
        estimated_delivery=row["estimated_delivery"],
        notes=row["notes"],
    )
    return OrderLookup(status="ok", message="Pedido localizado.", order=order)
