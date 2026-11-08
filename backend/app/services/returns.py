"""Elegibilidade de troca, devolução e garantia (manual, seções 4 e 8).

A conta de prazo é feita em código, nunca pelo LLM. O agente só verbaliza o
resultado. A data de "hoje" vem de app.core.clock (pode ser fixada por NOW_OVERRIDE).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from app.core.clock import get_now
from app.core.rules import (
    DEFECT_SWAP_WINDOW_DAYS,
    LEGAL_WARRANTY_DAYS,
    NON_RETURNABLE_KEYWORDS,
    PREFERENCE_WINDOW_DAYS,
    REFUND_BUSINESS_DAYS,
    REGRET_WINDOW_DAYS,
)
from app.core.text import normalize
from app.services.orders import lookup_order
from app.services.schemas import OrderInfo, ReturnEligibility, ReturnOutcome, ReturnReason

REFERENCE_ASSUMPTION = (
    "A base não registra a data real de recebimento; usamos a data prevista de entrega "
    "como referência de recebimento."
)
CHANNEL_ASSUMPTION = (
    "A base não informa o canal da compra; tratamos todos os pedidos como compras online "
    "(direito de arrependimento, seção 4.1)."
)
CONDITIONS_ORIGINAL_STATE = [
    "Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
]


def _fmt(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def _result(order_id: int, reason: ReturnReason, outcome: ReturnOutcome, eligible: bool | None, summary: str, **kw) -> ReturnEligibility:
    return ReturnEligibility(
        order_id=order_id, reason=reason, outcome=outcome, eligible=eligible, summary=summary, **kw
    )


def _restricted_items(order: OrderInfo) -> list[str]:
    return [
        item.name
        for item in order.items
        if any(k in normalize(item.name) for k in NON_RETURNABLE_KEYWORDS)
    ]


def check_return_eligibility(
    conn: sqlite3.Connection,
    order_id: int,
    reason: ReturnReason,
    email: str | None = None,
    phone: str | None = None,
    now: datetime | str | None = None,
) -> ReturnEligibility:
    """Aplica as regras de arrependimento, defeito ou preferência a um pedido."""
    lookup = lookup_order(conn, order_id, email=email, phone=phone)
    if lookup.status != "ok":
        return _result(order_id, reason, lookup.status, None, lookup.message)
    order = lookup.order
    assert order is not None
    today = get_now(now).date()

    if order.status == "cancelled":
        return _result(
            order_id, reason, "cancelled_order", False,
            "Este pedido foi cancelado, então não há compra a devolver ou trocar.",
        )

    if order.status in ("pending", "confirmed", "shipped"):
        steps = ["Quando o pedido for entregue, os prazos passam a contar a partir do recebimento."]
        if reason == "arrependimento":
            steps.append(
                "Se o cliente quer desistir antes da entrega, o cancelamento deve ser tratado "
                "pela equipe (o manual não define esse fluxo): encaminhar para atendimento humano."
            )
        return _result(
            order_id, reason, "not_delivered", None,
            f"O pedido ainda não foi entregue (status: {order.status_label.lower()}). "
            f"O prazo de {REGRET_WINDOW_DAYS} dias do arrependimento só começa no recebimento.",
            rule="4.1", next_steps=steps,
        )

    # --- Pedido entregue ---------------------------------------------------------
    if not order.estimated_delivery:
        return _result(
            order_id, reason, "needs_human", None,
            "Não há data de entrega registrada neste pedido, então não é possível calcular o prazo.",
            next_steps=["Encaminhar para atendimento humano."],
        )

    received = date.fromisoformat(order.estimated_delivery)
    purchased = date.fromisoformat(order.order_date)
    since_received = max(0, (today - received).days)
    since_purchase = max(0, (today - purchased).days)
    assumptions = [REFERENCE_ASSUMPTION]
    ref_label = "recebimento (estimado pela data prevista de entrega)"
    restricted = _restricted_items(order)

    if reason in ("arrependimento", "preferencia"):
        window = REGRET_WINDOW_DAYS if reason == "arrependimento" else PREFERENCE_WINDOW_DAYS
        rule = "4.1" if reason == "arrependimento" else "4.3"
        if reason == "arrependimento":
            assumptions.append(CHANNEL_ASSUMPTION)
        deadline = received + timedelta(days=window)

        if restricted:
            return _result(
                order_id, reason, "not_eligible", False,
                "Este pedido contém item não elegível para troca ou devolução por razões de "
                f"higiene (seção 4.4): {', '.join(restricted)}.",
                rule="4.4", assumptions=assumptions,
            )

        if since_received <= window:
            if reason == "arrependimento":
                conditions = CONDITIONS_ORIGINAL_STATE + [
                    f"Reembolso na mesma forma de pagamento original em até {REFUND_BUSINESS_DAYS} dias úteis.",
                    "O frete de devolução fica por conta da loja.",
                ]
                summary = (
                    f"Dentro do prazo: recebido em {_fmt(received)}, {since_received} dia(s) atrás; "
                    f"o direito de arrependimento vai até {_fmt(deadline)}."
                )
            else:
                conditions = CONDITIONS_ORIGINAL_STATE + [
                    "A troca depende da disponibilidade do produto desejado.",
                    "Diferenças de valor são cobradas ou reembolsadas conforme o caso.",
                ]
                summary = (
                    f"Dentro do prazo de troca por preferência (até {_fmt(deadline)}), "
                    "sujeita à disponibilidade do produto desejado."
                )
            return _result(
                order_id, reason, "eligible", True, summary, rule=rule,
                reference_date=received.isoformat(), reference_label=ref_label,
                days_elapsed=since_received, deadline=deadline.isoformat(),
                conditions=conditions, next_steps=["Encaminhar a solicitação para a equipe da loja."],
                assumptions=assumptions,
            )

        extra = []
        if since_received <= LEGAL_WARRANTY_DAYS:
            extra.append(
                "Se o motivo for defeito de fabricação, a garantia legal de 90 dias ainda está "
                "vigente: ofereça verificar essa opção."
            )
        return _result(
            order_id, reason, "not_eligible", False,
            f"Fora do prazo: o pedido foi recebido em {_fmt(received)} ({since_received} dias atrás) "
            f"e o prazo de {window} dias terminou em {_fmt(deadline)}.",
            rule=rule, reference_date=received.isoformat(), reference_label=ref_label,
            days_elapsed=since_received, deadline=deadline.isoformat(),
            next_steps=extra, assumptions=assumptions,
        )

    # --- Defeito de fabricação ------------------------------------------------------
    swap_deadline = purchased + timedelta(days=DEFECT_SWAP_WINDOW_DAYS)
    legal_deadline = received + timedelta(days=LEGAL_WARRANTY_DAYS)
    not_covered = (
        "Danos por mau uso, quedas, umidade excessiva ou modificações não autorizadas não são cobertos."
    )

    if since_purchase <= DEFECT_SWAP_WINDOW_DAYS:
        return _result(
            order_id, reason, "eligible", True,
            f"Dentro do prazo de troca por defeito de fabricação: {since_purchase} dia(s) desde a "
            f"compra; o prazo vai até {_fmt(swap_deadline)}.",
            rule="4.2", reference_date=purchased.isoformat(), reference_label="data da compra",
            days_elapsed=since_purchase, deadline=swap_deadline.isoformat(),
            conditions=[not_covered],
            next_steps=["Encaminhar a solicitação para a equipe da loja, com descrição do defeito."],
            assumptions=assumptions,
        )

    if since_received <= LEGAL_WARRANTY_DAYS:
        return _result(
            order_id, reason, "legal_warranty", None,
            f"O prazo de troca pela loja ({DEFECT_SWAP_WINDOW_DAYS} dias da compra) terminou em "
            f"{_fmt(swap_deadline)}, mas a garantia legal de {LEGAL_WARRANTY_DAYS} dias contra "
            f"defeito de fabricação vai até {_fmt(legal_deadline)}.",
            rule="4.2 e 8.1", reference_date=received.isoformat(), reference_label=ref_label,
            days_elapsed=since_received, deadline=legal_deadline.isoformat(),
            conditions=[not_covered],
            next_steps=[
                "Após os 30 dias, a garantia é acionada com o fabricante; a loja pode intermediar "
                "mediante solicitação do cliente.",
            ],
            assumptions=assumptions,
        )

    return _result(
        order_id, reason, "manufacturer_warranty", None,
        f"A garantia legal de {LEGAL_WARRANTY_DAYS} dias terminou em {_fmt(legal_deadline)}. "
        "Só resta a garantia do fabricante, que costuma variar de 6 meses a 2 anos conforme o "
        "certificado que acompanha o produto.",
        rule="8.2", reference_date=received.isoformat(), reference_label=ref_label,
        days_elapsed=since_received, deadline=legal_deadline.isoformat(),
        conditions=[not_covered],
        next_steps=["Consultar o certificado de garantia; a loja pode intermediar a pedido do cliente."],
        assumptions=assumptions,
    )
