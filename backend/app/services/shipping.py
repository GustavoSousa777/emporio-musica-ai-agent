"""Frete e prazos de entrega (manual, seção 5)."""
from __future__ import annotations

from app.core.money import f2, to_decimal
from app.core.rules import (
    CARRIERS,
    FLAT_SHIPPING_FEE,
    FREE_SHIPPING_ABOVE,
    LARGE_ITEM_KEYWORDS,
    METRO_CITIES,
    METRO_DELIVERY_DAYS,
)
from app.core.text import normalize
from app.services.schemas import ShippingOption, ShippingQuote


def is_large_item(product_name: str) -> bool:
    """Itens de grande porte exigem cotação individual (manual 5.2)."""
    name = normalize(product_name)
    return any(keyword in name for keyword in LARGE_ITEM_KEYWORDS)


def calculate_shipping(
    city: str | None, order_total: float, has_large_items: bool = False
) -> ShippingQuote:
    total = to_decimal(order_total)
    city_norm = normalize(city)
    notes: list[str] = []

    if has_large_items:
        notes.append(
            "Instrumentos de grande porte (baterias acústicas, pianos digitais, contrabaixos) "
            "podem exigir frete especial com cotação individual."
        )

    if not city_norm:
        notes.append("Informe a cidade de entrega para calcular o frete.")
        return ShippingQuote(
            region="desconhecida", city=None, order_total_brl=f2(total),
            options=[], requires_special_quote=has_large_items, notes=notes,
        )

    if city_norm in METRO_CITIES:
        free = total > FREE_SHIPPING_ABOVE
        cost = 0.0 if free else f2(FLAT_SHIPPING_FEE)
        notes.append("Entrega por motoboy próprio; o cliente recebe uma ligação antes da entrega.")
        if not free:
            notes.append("Frete grátis para pedidos acima de R$ 500,00.")
        return ShippingQuote(
            region="metropolitana",
            city=city,
            order_total_brl=f2(total),
            options=[ShippingOption(carrier="Motoboy próprio", deadline=METRO_DELIVERY_DAYS, cost_brl=cost)],
            requires_special_quote=has_large_items,
            notes=notes,
        )

    notes.append("Todos os envios incluem rastreamento e seguro contra extravio e danos.")
    notes.append("Em caso de avaria, recuse o recebimento e avise a loja imediatamente.")
    return ShippingQuote(
        region="outras_cidades",
        city=city,
        order_total_brl=f2(total),
        options=[
            ShippingOption(
                carrier=c["name"],
                deadline=c["deadline"],
                cost_brl=None,
                cost_note="Calculado automaticamente por CEP, peso e dimensões no fechamento do pedido.",
            )
            for c in CARRIERS
        ],
        requires_special_quote=has_large_items,
        notes=notes,
    )
