"""Regras de negócio do Manual de Políticas e Procedimentos (v2.1, jun/2025).

Cada constante cita a seção de origem. Onde o manual é ambíguo ou se contradiz,
a interpretação adotada está marcada como ASSUMPTION e listada em docs/premissas.md.
"""
from __future__ import annotations

from datetime import time
from decimal import Decimal

# --- Loja (seções 1 e 2) -------------------------------------------------------
STORE_INFO = {
    "name": "Empório da Música",
    "tagline": "Sua música começa aqui.",
    "address": "Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333",
    "city": "Campo Grande",
    "state": "MS",
    # ASSUMPTION: o manual traz dois telefones. A capa e a seção 1.2 informam
    # (67) 3341-4444 como telefone/WhatsApp; a seção 7 cita o WhatsApp
    # (67) 3321-4500. Expomos os dois, com o rótulo de cada fonte.
    "phone": "(67) 3341-4444",
    "whatsapp": "(67) 3321-4500",
    # ASSUMPTION: a seção 1.2 grafa "empóriodamusica" com acento (erro de digitação).
    # Usamos o e-mail da capa, sem acento.
    "email": "contato@emporiodamusica.com.br",
    "founded": 2008,
}

# weekday(): segunda=0 ... domingo=6. None = fechado.
OPENING_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(9, 0), time(18, 0)),
    1: (time(9, 0), time(18, 0)),
    2: (time(9, 0), time(18, 0)),
    3: (time(9, 0), time(18, 0)),
    4: (time(9, 0), time(18, 0)),
    5: (time(9, 0), time(13, 0)),
    6: None,
}

SOLD_CATEGORIES_NOTE = (
    "A loja trabalha exclusivamente com instrumentos musicais. Não vende "
    "acessórios (cordas, palhetas, cabos, cases, pedais ou amplificadores)."
)

# --- Pagamento (seção 3) ----------------------------------------------------------
PIX_DISCOUNT_PERCENT = Decimal("5")
MAX_INSTALLMENTS = 12
# "Combinação de formas de pagamento: permitida para compras acima de R$ 2.000,00"
COMBINED_PAYMENT_MIN_TOTAL = Decimal("2000")
BOLETO_CLEARING_BUSINESS_DAYS = 3


def min_installment_value(installments: int) -> Decimal:
    """Parcela mínima por faixa (seção 3.1).

    ASSUMPTION: a tabela da seção 3 diz "parcela mínima de R$ 100" para todo o
    crédito, mas a seção 3.1 detalha por faixa. Adotamos a 3.1 por ser a regra
    mais específica:
      1x: sem mínimo | 2x-3x: parcela >= R$ 50 | 4x-6x: >= R$ 80 | 7x-12x: >= R$ 100
    """
    if installments <= 1:
        return Decimal("0")
    if installments <= 3:
        return Decimal("50")
    if installments <= 6:
        return Decimal("80")
    return Decimal("100")


# --- Frete (seção 5) -------------------------------------------------------------
# "Frete grátis para pedidos acima de R$ 500,00": acima, ou seja, > 500.
FREE_SHIPPING_ABOVE = Decimal("500")
FLAT_SHIPPING_FEE = Decimal("35")
METRO_DELIVERY_DAYS = "1 a 3 dias úteis"
# ASSUMPTION: o manual não define "Região Metropolitana". Consideramos apenas
# Campo Grande (as demais cidades da base de clientes são tratadas como "outras").
METRO_CITIES = frozenset({"campo grande"})
CARRIERS = (
    {"name": "PAC (Correios)", "deadline": "5 a 12 dias úteis", "tracking": True, "insured": True},
    {"name": "SEDEX (Correios)", "deadline": "2 a 5 dias úteis", "tracking": True, "insured": True},
    {"name": "Jadlog (.package)", "deadline": "3 a 8 dias úteis", "tracking": True, "insured": True},
)
LARGE_ITEM_KEYWORDS = ("bateria acustica", "piano", "contrabaixo")

# --- Trocas, devoluções e garantia (seções 4 e 8) ------------------------------
REGRET_WINDOW_DAYS = 7        # 4.1, a partir do recebimento
PREFERENCE_WINDOW_DAYS = 7    # 4.3
DEFECT_SWAP_WINDOW_DAYS = 30  # 4.2, a partir da compra
LEGAL_WARRANTY_DAYS = 90      # 8.1, a partir do recebimento
REFUND_BUSINESS_DAYS = 10     # 4.1
NON_RETURNABLE_KEYWORDS = ("boquilha",)  # 4.4 (higiene)

# --- Pedidos -----------------------------------------------------------------------
ORDER_STATUSES = ("pending", "confirmed", "shipped", "delivered", "cancelled")
PRODUCT_STATUSES = ("active", "discontinued", "coming_soon")
TRACKING_CODE_PATTERN = r"^BR[A-Z0-9]{9}BR$"  # 5.3
