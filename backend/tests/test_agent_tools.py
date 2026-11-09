from __future__ import annotations

import json

import pytest

from app.agent.tools import TOOLS, ToolContext, Toolset, clean_schema

EMAIL_1 = "pedro.oliveira@jmail.com"
NOW = "2026-03-23T10:00:00"  # segunda-feira


@pytest.fixture()
def ctx(conn, retriever, conversations):
    return ToolContext(conn, retriever, conversations, "sessao-teste", now=None)


@pytest.fixture()
def toolset():
    return Toolset()


def test_todas_as_ferramentas_tem_schema_compativel_com_o_gemini():
    forbidden = {"anyOf", "title", "default", "$defs", "exclusiveMinimum"}

    def walk(node):
        assert not forbidden & set(node), node
        for prop in node.get("properties", {}).values():
            walk(prop)

    for spec in TOOLS:
        schema = spec.parameters
        assert schema["type"] == "object"
        walk(schema)
        assert spec.description.strip()


def test_campo_opcional_fica_fora_de_required():
    schema = next(t for t in TOOLS if t.name == "get_order_status").parameters
    assert schema["required"] == ["order_id"]
    assert schema["properties"]["email"]["type"] == "string"


def test_clean_schema_converte_exclusive_minimum():
    out = clean_schema({"type": "object", "properties": {"a": {"type": "number", "exclusiveMinimum": 0, "title": "A"}}})
    assert out["properties"]["a"] == {"type": "number", "minimum": 0}


def test_busca_de_produto_nao_inventa_promocao_inativa(toolset, ctx):
    result, ok = toolset.run("search_products", {"query": "Takamine GD20"}, ctx)
    product = result["products"][0]
    assert ok and product["product_id"] == 95
    assert product["promotion"] is None and product["final_price_brl"] == 2199.0


def test_listagem_por_faixa_de_preco(toolset, ctx):
    result, ok = toolset.run("search_products", {"category": "violões", "max_price": 1000}, ctx)
    assert ok and result["products"]
    assert all(p["final_price_brl"] <= 1000 for p in result["products"])


def test_categorias(toolset, ctx):
    result, ok = toolset.run("list_categories", {}, ctx)
    assert ok and len(result["categories"]) >= 6


def test_status_de_promocao_de_produto_inexistente(toolset, ctx):
    result, ok = toolset.run("get_promotion_status", {"product_id": 99999}, ctx)
    assert not ok and "error" in result


def test_opcoes_de_pagamento_pix_so_sem_promocao(toolset, ctx):
    normal, _ = toolset.run("get_payment_options", {"amount": 2000}, ctx)
    promo, _ = toolset.run("get_payment_options", {"amount": 2000, "promotional": True}, ctx)
    assert normal["pix_discount_applied"] and normal["pix_total_brl"] == 1900.0
    assert not promo["pix_discount_applied"] and promo["pix_total_brl"] is None
    assert any("não se aplica a preços já promocionais" in n for n in promo["notes"])


def test_frete_campo_grande_gratis_acima_de_500(toolset, ctx):
    free, _ = toolset.run("calculate_shipping", {"city": "Campo Grande", "order_total": 600}, ctx)
    fee, _ = toolset.run("calculate_shipping", {"city": "Campo Grande", "order_total": 300}, ctx)
    assert free["options"][0]["cost_brl"] == 0.0 and fee["options"][0]["cost_brl"] == 35.0


def test_horario_da_loja(toolset, ctx):
    ctx.now = NOW
    result, ok = toolset.run("get_opening_status", {}, ctx)
    assert ok and result["is_open"] is False or result["weekday"] == "segunda-feira"


def test_pedido_exige_verificacao(toolset, ctx):
    sem, _ = toolset.run("get_order_status", {"order_id": 1}, ctx)
    errado, _ = toolset.run("get_order_status", {"order_id": 1, "email": "outro@jmail.com"}, ctx)
    certo, _ = toolset.run("get_order_status", {"order_id": 1, "email": EMAIL_1}, ctx)
    assert sem["status"] == "verification_required"
    assert errado["status"] == "not_verified" and errado["order"] is None
    assert certo["status"] == "ok" and certo["order"]["order_id"] == 1


def test_verificacao_falha_nao_vaza_nome_do_cliente(toolset, ctx):
    errado, _ = toolset.run("get_order_status", {"order_id": 1, "email": "outro@jmail.com"}, ctx)
    assert "Pedro" not in json.dumps(errado, ensure_ascii=False)


def test_elegibilidade_de_devolucao_usa_a_data_de_hoje(toolset, ctx):
    ctx.now = "2025-10-26T10:00:00"  # um dia depois do recebimento do pedido 1
    dentro, _ = toolset.run("check_return_eligibility", {"order_id": 1, "email": EMAIL_1, "reason": "arrependimento"}, ctx)
    ctx.now = "2026-03-23T10:00:00"
    fora, _ = toolset.run("check_return_eligibility", {"order_id": 1, "email": EMAIL_1, "reason": "arrependimento"}, ctx)
    assert dentro["outcome"] == "eligible" and fora["outcome"] == "not_eligible"


def test_busca_de_politicas_devolve_trechos(toolset, ctx):
    result, ok = toolset.run("search_policies", {"query": "prazo para trocar por defeito"}, ctx)
    assert ok and result["hits"][0]["section"] == "4.2"


def test_busca_de_politicas_sem_resposta_orienta_escalonamento(toolset, ctx):
    result, ok = toolset.run("search_policies", {"query": "capital da França"}, ctx)
    assert ok and result["hits"] == [] and "escalate_to_human" in result["note"]


def test_escalonamento_registra_protocolo(toolset, ctx, conversations):
    ctx.now = NOW
    result, ok = toolset.run(
        "escalate_to_human",
        {"reason": "complaint", "summary": "Cliente reclama de atraso na entrega do pedido 8", "order_id": 8},
        ctx,
    )
    assert ok and result["registered"] and result["protocol"] == "ATD-00001"
    assert result["response_time"] == "24 horas úteis"
    handoffs = conversations.list_handoffs()
    assert len(handoffs) == 1 and handoffs[0]["session_id"] == "sessao-teste" and handoffs[0]["order_id"] == 8


def test_escalonamento_que_nao_e_reclamacao_nao_promete_prazo(toolset, ctx):
    result, _ = toolset.run("escalate_to_human", {"reason": "human_requested", "summary": "Quer falar com um atendente"}, ctx)
    assert result["response_time"] is None


def test_argumentos_invalidos_viram_erro_para_o_modelo(toolset, ctx):
    result, ok = toolset.run("get_payment_options", {"amount": -5}, ctx)
    assert not ok and "inválidos" in result["error"]
    result, ok = toolset.run("check_return_eligibility", {"order_id": 1, "email": EMAIL_1, "reason": "gostei menos"}, ctx)
    assert not ok


def test_ferramenta_desconhecida(toolset, ctx):
    result, ok = toolset.run("apagar_banco", {}, ctx)
    assert not ok and "desconhecida" in result["error"]


def test_falha_interna_nao_derruba_a_conversa(toolset, ctx, monkeypatch):
    from app.agent import tools

    def boom(*args, **kwargs):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(tools.products, "search_products", boom)
    result, ok = toolset.run("search_products", {"query": "violão"}, ctx)
    assert not ok and "Não consegui" in result["error"] and "disco" not in result["error"]
