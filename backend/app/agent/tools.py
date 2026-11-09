"""Ferramentas (function calling) que o agente pode chamar.

Cada ferramenta é uma função fina sobre os serviços determinísticos de app/services
(ou sobre o RAG). Os argumentos são validados com Pydantic, e o mesmo modelo gera o
JSON Schema enviado ao Gemini, então não há duas definições para manter em sincronia.

O LLM nunca escreve SQL: só escolhe a ferramenta e os argumentos.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, ValidationError

from app.agent.memory import ConversationStore
from app.core.rules import STORE_INFO
from app.rag.retriever import Retriever
from app.services import orders, payments, products, promotions, returns, shipping, store

logger = logging.getLogger(__name__)

HandoffReason = Literal[
    "complaint", "return_request", "order_change", "policy_doubt",
    "special_shipping_quote", "human_requested", "other",
]
COMPLAINT_RESPONSE_TIME = "24 horas úteis"  # manual, seção 7.3


@dataclass
class ToolContext:
    conn: sqlite3.Connection
    retriever: Retriever
    store: ConversationStore
    session_id: str
    now: datetime | None = None


# --- Argumentos ----------------------------------------------------------------------
class SearchProductsArgs(BaseModel):
    query: str | None = Field(None, description="Nome, marca ou modelo ('Takamine GD20', 'ukulele soprano'). Omita para listar por filtros.")
    category: str | None = Field(None, description="Categoria ('violões', 'guitarras', 'baixos', 'ukuleles', 'teclados', 'baterias'). Use list_categories se tiver dúvida.")
    min_price: float | None = Field(None, ge=0, description="Preço mínimo em reais, já considerando promoção ativa.")
    max_price: float | None = Field(None, ge=0, description="Preço máximo em reais, já considerando promoção ativa. Ex.: 'até R$1000' vira 1000.")
    available_only: bool | None = Field(None, description="True só mostra o que está em estoque. Omita: listagens mostram só disponíveis, buscas por nome mostram também esgotados e descontinuados.")
    on_promotion_only: bool = Field(False, description="True lista só produtos em promoção ativa.")


class EmptyArgs(BaseModel):
    pass


class PromotionArgs(BaseModel):
    product_id: int = Field(description="ID do produto (campo product_id de search_products).")


class PaymentArgs(BaseModel):
    amount: float = Field(gt=0, description="Valor total em reais (use o preço final do produto).")
    promotional: bool = Field(False, description="True se o valor já é preço promocional (o PIX não tem desconto nesse caso).")


class ShippingArgs(BaseModel):
    city: str | None = Field(None, description="Cidade de entrega. Pergunte ao cliente se não souber.")
    order_total: float = Field(ge=0, description="Valor dos produtos em reais.")
    has_large_items: bool = Field(False, description="True se houver bateria acústica, piano digital ou contrabaixo.")


class OrderArgs(BaseModel):
    order_id: int = Field(description="Número do pedido informado pelo cliente.")
    email: str | None = Field(None, description="E-mail cadastrado na compra.")
    phone: str | None = Field(None, description="Telefone cadastrado na compra.")


class ReturnArgs(OrderArgs):
    reason: Literal["arrependimento", "defeito", "preferencia"] = Field(
        description="arrependimento: desistiu da compra online; defeito: defeito de fabricação; preferencia: trocar por outra cor ou modelo."
    )


class PolicyArgs(BaseModel):
    query: str = Field(min_length=3, description="Pergunta do cliente reescrita de forma clara, em português.")


class EscalateArgs(BaseModel):
    reason: HandoffReason = Field(description="complaint: reclamação; return_request: cliente quer prosseguir com devolução ou troca; order_change: alterar ou cancelar pedido; policy_doubt: dúvida de política sem resposta; special_shipping_quote: frete de item grande; human_requested: pediu atendente; other.")
    summary: str = Field(min_length=10, description="Resumo objetivo do caso para a equipe, com o que o cliente quer e o que já foi verificado. Sem senhas nem dados de cartão.")
    customer_name: str | None = Field(None, description="Nome do cliente, se informado.")
    contact: str | None = Field(None, description="E-mail ou telefone para retorno, se o cliente informar.")
    order_id: int | None = Field(None, description="Número do pedido relacionado, se houver.")


# --- Handlers ------------------------------------------------------------------------
def _search_products(ctx: ToolContext, a: SearchProductsArgs):
    return products.search_products(ctx.conn, **a.model_dump(exclude_none=True))


def _list_categories(ctx: ToolContext, a: EmptyArgs):
    return {"categories": products.list_categories(ctx.conn)}


def _promotion_status(ctx: ToolContext, a: PromotionArgs):
    status = promotions.get_promotion_status(ctx.conn, a.product_id)
    return status if status else {"error": f"Produto {a.product_id} não encontrado."}


def _payment_options(ctx: ToolContext, a: PaymentArgs):
    return payments.get_payment_options(a.amount, promotional=a.promotional)


def _shipping(ctx: ToolContext, a: ShippingArgs):
    return shipping.calculate_shipping(a.city, a.order_total, a.has_large_items)


def _store_info(ctx: ToolContext, a: EmptyArgs):
    return store.get_store_info()


def _opening_status(ctx: ToolContext, a: EmptyArgs):
    return store.get_opening_status(ctx.now)


def _order_status(ctx: ToolContext, a: OrderArgs):
    return orders.lookup_order(ctx.conn, a.order_id, email=a.email, phone=a.phone)


def _return_eligibility(ctx: ToolContext, a: ReturnArgs):
    return returns.check_return_eligibility(
        ctx.conn, a.order_id, a.reason, email=a.email, phone=a.phone, now=ctx.now
    )


def _search_policies(ctx: ToolContext, a: PolicyArgs):
    hits = ctx.retriever.search(a.query, k=4)
    if not hits:
        return {
            "query": a.query,
            "hits": [],
            "note": "Nenhum trecho do manual responde a essa pergunta. Diga ao cliente que não tem essa informação "
            "e ofereça encaminhar à equipe (escalate_to_human, reason=policy_doubt).",
        }
    return {"query": a.query, "hits": [h.to_dict() for h in hits]}


def _escalate(ctx: ToolContext, a: EscalateArgs):
    handoff_id = ctx.store.create_handoff(
        ctx.session_id, a.reason, a.summary, a.customer_name, a.contact, a.order_id
    )
    opening = store.get_opening_status(ctx.now)
    return {
        "registered": True,
        "protocol": f"ATD-{handoff_id:05d}",
        "response_time": COMPLAINT_RESPONSE_TIME if a.reason == "complaint" else None,
        "store_status": opening.message,
        "contact": {"phone": STORE_INFO["phone"], "whatsapp": STORE_INFO["whatsapp"], "email": STORE_INFO["email"]},
        "note": "Informe o protocolo ao cliente. O manual só define prazo para reclamações; para os demais casos "
        "diga que a equipe retornará, sem prometer horário.",
    }


# --- Registro ------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], Any]

    @property
    def parameters(self) -> dict[str, Any]:
        return clean_schema(self.args_model.model_json_schema())


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "search_products",
        "Busca produtos do catálogo com preço, estoque, promoção ativa e especificações. Use para qualquer pergunta sobre "
        "produto, preço, disponibilidade ou recomendação. Preços e estoque só podem ser informados a partir deste resultado.",
        SearchProductsArgs, _search_products,
    ),
    ToolSpec("list_categories", "Lista as categorias do catálogo e quantos produtos disponíveis cada uma tem.", EmptyArgs, _list_categories),
    ToolSpec(
        "get_promotion_status",
        "Situação das promoções de um produto: ativa (com preço original, percentual e preço final) ou encerrada. "
        "Use quando o cliente perguntar de uma promoção específica.",
        PromotionArgs, _promotion_status,
    ),
    ToolSpec(
        "get_payment_options",
        "Formas de pagamento para um valor: preço no PIX, débito, boleto e parcelas possíveis no crédito (sem juros), "
        "respeitando a parcela mínima. Use para dúvidas de parcelamento e condições de pagamento de um valor.",
        PaymentArgs, _payment_options,
    ),
    ToolSpec(
        "calculate_shipping",
        "Frete e prazo de entrega por cidade e valor do pedido. Campo Grande: motoboy, grátis acima de R$ 500. "
        "Outras cidades: Correios e Jadlog, com prazos (o valor sai no fechamento do pedido).",
        ShippingArgs, _shipping,
    ),
    ToolSpec("get_store_info", "Endereço, telefone, WhatsApp, e-mail e horários de funcionamento da loja.", EmptyArgs, _store_info),
    ToolSpec(
        "get_opening_status",
        "Informa se a loja está aberta agora, o horário de hoje, feriados e quando reabre. Use para 'está aberto?' "
        "e para dizer quando a equipe retorna.",
        EmptyArgs, _opening_status,
    ),
    ToolSpec(
        "get_order_status",
        "Consulta status, itens, pagamento, rastreio e previsão de entrega de um pedido. Exige o número do pedido e o "
        "e-mail ou telefone cadastrados; sem isso a consulta é recusada.",
        OrderArgs, _order_status,
    ),
    ToolSpec(
        "check_return_eligibility",
        "Verifica se um pedido pode ser devolvido ou trocado (arrependimento, defeito ou preferência), calculando prazos "
        "pela data de hoje. Exige número do pedido e e-mail ou telefone cadastrados.",
        ReturnArgs, _return_eligibility,
    ),
    ToolSpec(
        "search_policies",
        "Busca no manual de políticas da loja (trocas, garantia, pagamento, frete, promoções, privacidade, horários). "
        "Use para dúvidas sobre regras e procedimentos. Responda só com o que os trechos disserem.",
        PolicyArgs, _search_policies,
    ),
    ToolSpec(
        "escalate_to_human",
        "Registra o caso para a equipe humana e gera um protocolo. Use para reclamações, pedidos de devolução ou troca a "
        "prosseguir, alterações ou cancelamentos de pedido, dúvidas de política sem resposta, frete de item grande e quando "
        "o cliente pedir um atendente.",
        EscalateArgs, _escalate,
    ),
)

_ALLOWED_SCHEMA_KEYS = {"type", "description", "enum", "properties", "required", "items", "minimum", "maximum", "minLength"}


def clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Reduz o JSON Schema do Pydantic ao subconjunto aceito pelo Gemini.

    Remove title/default, transforma `X | None` em `X` (campo opcional = fora de `required`)
    e converte `gt` em minimum.
    """

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            merged = {**{k: v for k, v in node.items() if k != "anyOf"}, **(options[0] if options else {})}
            return convert(merged)
        if "exclusiveMinimum" in node:
            node = {**node, "minimum": node["exclusiveMinimum"]}
        out = {k: v for k, v in node.items() if k in _ALLOWED_SCHEMA_KEYS}
        if "properties" in out:
            out["properties"] = {name: convert(prop) for name, prop in out["properties"].items()}
        if "items" in out:
            out["items"] = convert(out["items"])
        return out

    result = convert(schema)
    result.setdefault("type", "object")
    result.setdefault("properties", {})
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class Toolset:
    def __init__(self, specs: tuple[ToolSpec, ...] = TOOLS):
        self.specs = specs
        self._by_name = {s.name: s for s in specs}

    def run(self, name: str, args: dict[str, Any], ctx: ToolContext) -> tuple[dict[str, Any], bool]:
        """Executa uma ferramenta. Nunca levanta: erros viram {"error": ...} para o modelo."""
        spec = self._by_name.get(name)
        if spec is None:
            return {"error": f"Ferramenta desconhecida: {name}."}, False
        try:
            parsed = spec.args_model.model_validate(args or {})
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            return {"error": f"Argumentos inválidos ({problems}). Corrija e tente de novo."}, False
        try:
            result = _jsonable(spec.handler(ctx, parsed))
        except Exception:  # noqa: BLE001 - a conversa não pode cair por falha de ferramenta
            logger.exception("Falha na ferramenta %s", name)
            return {"error": "Não consegui consultar essa informação agora."}, False
        result = result if isinstance(result, dict) else {"result": result}
        return result, "error" not in result
