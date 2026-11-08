"""Formas de pagamento e parcelamento (manual, seção 3)."""
from __future__ import annotations

from decimal import Decimal

from app.core.money import brl, f2, q2, to_decimal
from app.core.rules import (
    BOLETO_CLEARING_BUSINESS_DAYS,
    COMBINED_PAYMENT_MIN_TOTAL,
    MAX_INSTALLMENTS,
    PIX_DISCOUNT_PERCENT,
    min_installment_value,
)
from app.services.schemas import InstallmentOption, PaymentOptions


def pix_price(list_price: float | Decimal) -> float:
    """Preço no PIX: 5% sobre o preço de tabela."""
    return f2(to_decimal(list_price) * (Decimal(100) - PIX_DISCOUNT_PERCENT) / Decimal(100))


def validate_installment(amount: float | Decimal, installments: int) -> tuple[bool, str, float]:
    """Verifica se o parcelamento é permitido. Retorna (ok, motivo, valor da parcela)."""
    if installments < 1 or installments > MAX_INSTALLMENTS:
        return False, f"O parcelamento vai de 1x a {MAX_INSTALLMENTS}x.", 0.0
    value = q2(to_decimal(amount) / installments)
    minimum = min_installment_value(installments)
    if value < minimum:
        return (
            False,
            f"Em {installments}x a parcela ficaria {brl(value)}, abaixo do mínimo de {brl(minimum)}.",
            float(value),
        )
    return True, "ok", float(value)


def get_payment_options(amount: float | Decimal, promotional: bool = False) -> PaymentOptions:
    """Todas as formas de pagamento para um valor.

    promotional=True indica que o valor já é preço promocional: o desconto do PIX
    não se aplica (manual 6.2, promoções não são cumulativas).
    """
    total = q2(amount)
    credit = []
    for n in range(1, MAX_INSTALLMENTS + 1):
        ok, _, value = validate_installment(total, n)
        if ok:
            credit.append(InstallmentOption(installments=n, installment_value_brl=value, total_brl=float(total)))

    notes = [
        "Cartão de crédito parcelado sem juros.",
        f"Boleto à vista, compensação em até {BOLETO_CLEARING_BUSINESS_DAYS} dias úteis.",
    ]
    if promotional:
        notes.append("O desconto de 5% no PIX não se aplica a preços já promocionais.")
    combine = total > COMBINED_PAYMENT_MIN_TOTAL
    notes.append(
        "É possível combinar formas de pagamento (ex.: PIX + cartão)."
        if combine
        else "Combinar formas de pagamento só é permitido em compras acima de R$ 2.000,00."
    )

    return PaymentOptions(
        amount_brl=float(total),
        pix_total_brl=None if promotional else pix_price(total),
        pix_discount_applied=not promotional,
        debit_total_brl=float(total),
        boleto_total_brl=float(total),
        credit=credit,
        max_installments=max((c.installments for c in credit), default=1),
        can_combine_payment_methods=combine,
        notes=notes,
    )
