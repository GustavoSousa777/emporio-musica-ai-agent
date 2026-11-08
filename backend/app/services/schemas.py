"""Modelos de saída dos serviços (o agente recebe estes objetos como JSON)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Availability = Literal["available", "out_of_stock", "discontinued", "coming_soon"]


# --- Promoções e produtos -----------------------------------------------------------
class PromotionInfo(BaseModel):
    promotion_id: int
    label: str
    discount_percent: float
    original_price_brl: float
    final_price_brl: float
    savings_brl: float
    summary: str = Field(description="Texto pronto: preço original, desconto e preço final (manual 6.2)")


class ExpiredPromotion(BaseModel):
    promotion_id: int
    label: str
    discount_percent: float


class PromotionStatus(BaseModel):
    product_id: int
    product_name: str
    current_price_brl: float
    active: PromotionInfo | None
    expired: list[ExpiredPromotion]
    message: str


class ProductInfo(BaseModel):
    product_id: int
    name: str
    category_id: int
    category: str
    description: str | None
    status: str
    availability: Availability
    stock_quantity: int
    price_brl: float = Field(description="Preço de tabela")
    promotion: PromotionInfo | None
    final_price_brl: float = Field(description="Preço a pagar (com promoção ativa, se houver)")
    pix_price_brl: float | None = Field(description="Preço no PIX; None quando há promoção (não cumulativo)")
    price_summary: str
    specs: dict[str, Any]


class ProductSearchResult(BaseModel):
    query: str | None
    filters: dict[str, Any]
    total_matches: int
    products: list[ProductInfo]
    alternatives: list[ProductInfo] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CategoryInfo(BaseModel):
    category_id: int
    name: str
    total_products: int
    available_products: int


# --- Pedidos e devoluções ----------------------------------------------------------
class OrderItemInfo(BaseModel):
    product_id: int
    name: str
    quantity: int


class OrderInfo(BaseModel):
    order_id: int
    customer_first_name: str
    order_date: str
    status: str
    status_label: str
    status_explanation: str
    items: list[OrderItemInfo]
    total_brl: float
    payment_method_label: str
    tracking_code: str | None
    estimated_delivery: str | None
    notes: str | None


class OrderLookup(BaseModel):
    status: Literal["ok", "verification_required", "not_verified"]
    message: str
    order: OrderInfo | None = None


ReturnReason = Literal["arrependimento", "defeito", "preferencia"]
ReturnOutcome = Literal[
    "eligible",
    "not_eligible",
    "legal_warranty",
    "manufacturer_warranty",
    "not_delivered",
    "cancelled_order",
    "needs_human",
    "verification_required",
    "not_verified",
]


class ReturnEligibility(BaseModel):
    order_id: int
    reason: ReturnReason
    outcome: ReturnOutcome
    eligible: bool | None
    summary: str
    rule: str | None = None
    reference_date: str | None = None
    reference_label: str | None = None
    days_elapsed: int | None = None
    deadline: str | None = None
    conditions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# --- Pagamento, frete e loja -------------------------------------------------------
class InstallmentOption(BaseModel):
    installments: int
    installment_value_brl: float
    total_brl: float


class PaymentOptions(BaseModel):
    amount_brl: float
    pix_total_brl: float | None
    pix_discount_applied: bool
    debit_total_brl: float
    boleto_total_brl: float
    credit: list[InstallmentOption]
    max_installments: int
    can_combine_payment_methods: bool
    notes: list[str]


class ShippingOption(BaseModel):
    carrier: str
    deadline: str
    cost_brl: float | None
    cost_note: str | None = None


class ShippingQuote(BaseModel):
    region: Literal["metropolitana", "outras_cidades", "desconhecida"]
    city: str | None
    order_total_brl: float
    options: list[ShippingOption]
    requires_special_quote: bool
    notes: list[str]


class StoreInfo(BaseModel):
    name: str
    tagline: str
    address: str
    phone: str
    whatsapp: str
    email: str
    founded: int
    opening_hours: list[dict[str, str]]
    scope_note: str


class OpeningStatus(BaseModel):
    now: str
    is_open: bool
    weekday: str
    todays_hours: str | None
    holiday: str | None
    next_opening: str | None
    message: str
