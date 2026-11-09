"""Loop do agente com um LLM roteirizado (sem rede): ferramentas, memória, escalonamento e falhas."""
from __future__ import annotations

import pytest

from app.agent.agent import (
    EMPTY_INPUT_MESSAGE,
    MAX_INPUT_CHARS,
    MAX_TOOL_ROUNDS,
    NO_ANSWER_MESSAGE,
    UNAVAILABLE_MESSAGE,
    Agent,
)
from app.agent.models import LLMTurn, ToolCall
from app.core.gemini_failover import LLMUnavailableError


class ScriptedLLM:
    """Devolve turnos pré-definidos e guarda o que recebeu."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def generate(self, messages, system, tools):
        self.calls.append({"messages": list(messages), "system": system, "tools": tools})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def say(text, model="m1"):
    return LLMTurn(text=text, tool_calls=[], model=model)


def call(name, **args):
    return LLMTurn(text="", tool_calls=[ToolCall(name, args)], model="m1")


@pytest.fixture()
def make_agent(db_path, retriever, conversations):
    def factory(turns):
        llm = ScriptedLLM(turns)
        return Agent(llm, retriever, conversations, db_path=db_path, now="2026-03-23T10:00:00"), llm

    return factory


def test_resposta_simples_e_persistida(make_agent, conversations):
    agent, llm = make_agent([say("Oi! Como posso ajudar?")])
    reply = agent.reply("s1", "Oi")
    assert reply.text == "Oi! Como posso ajudar?" and reply.tools == [] and not reply.degraded
    assert [m.role for m in conversations.history("s1")] == ["user", "assistant"]


def test_prompt_de_sistema_traz_persona_data_e_contato(make_agent):
    agent, llm = make_agent([say("ok")])
    agent.reply("s1", "Oi")
    system = llm.calls[0]["system"]
    assert "Empório da Música" in system and "23/03/2026 10:00" in system and "segunda-feira" in system
    assert "(67) 3321-4500" in system
    assert len(llm.calls[0]["tools"]) == 11


def test_loop_de_ferramentas_executa_e_devolve_resultado_ao_modelo(make_agent):
    agent, llm = make_agent([call("search_policies", query="prazo de troca por defeito"), say("São 30 dias corridos.")])
    reply = agent.reply("s1", "Qual o prazo para trocar por defeito?")
    assert reply.text == "São 30 dias corridos."
    assert [t.name for t in reply.tools] == ["search_policies"] and reply.tools[0].ok
    second = llm.calls[1]["messages"]
    assert [m.role for m in second] == ["user", "assistant", "tool"]
    assert second[2].tool_results[0].response["hits"][0]["section"] == "4.2"


def test_varias_rodadas_de_ferramentas(make_agent):
    agent, llm = make_agent([
        call("search_products", query="Takamine GD20"),
        call("get_payment_options", amount=2199.0),
        say("Dá para parcelar em até 12x."),
    ])
    reply = agent.reply("s1", "Quanto fica a Takamine GD20 parcelada?")
    assert [t.name for t in reply.tools] == ["search_products", "get_payment_options"]
    assert len(llm.calls) == 3


def test_erro_de_ferramenta_vai_para_o_modelo_sem_quebrar(make_agent):
    agent, llm = make_agent([call("get_payment_options", amount=-1), say("Pode me confirmar o valor?")])
    reply = agent.reply("s1", "Quero parcelar")
    assert not reply.tools[0].ok and reply.text == "Pode me confirmar o valor?"
    assert "error" in llm.calls[1]["messages"][2].tool_results[0].response


def test_escalonamento_marca_a_resposta_e_registra_o_caso(make_agent, conversations):
    agent, _ = make_agent([
        call("escalate_to_human", reason="complaint", summary="Cliente reclama do atendimento na loja"),
        say("Registrei sua reclamação. Protocolo ATD-00001."),
    ])
    reply = agent.reply("s1", "Quero reclamar do atendimento")
    assert reply.escalated and conversations.list_handoffs()[0]["reason"] == "complaint"


def test_dados_do_cliente_sao_mascarados_no_rastro(make_agent):
    agent, _ = make_agent([
        call("get_order_status", order_id=1, email="pedro.oliveira@jmail.com", phone="(67) 98432-1098"),
        say("Seu pedido foi entregue."),
    ])
    trace = agent.reply("s1", "Cadê meu pedido 1?").tools[0]
    assert trace.args["email"] == "***" and trace.args["phone"] == "***" and trace.args["order_id"] == 1


def test_memoria_por_session_id_e_isolada(make_agent):
    agent, llm = make_agent([say("Olá!"), say("Claro, o pedido 8."), say("Oi!")])
    agent.reply("sessao-a", "Quero saber do pedido 8")
    agent.reply("sessao-a", "É o do violão")
    second_call = llm.calls[1]["messages"]
    assert [m.text for m in second_call] == ["Quero saber do pedido 8", "Olá!", "É o do violão"]
    agent.reply("sessao-b", "Oi")
    assert [m.text for m in llm.calls[2]["messages"]] == ["Oi"]


def test_llm_indisponivel_devolve_aviso_e_nao_grava_a_conversa(make_agent, conversations):
    agent, _ = make_agent([LLMUnavailableError("sem cota", wait_seconds=3600, daily_quota=True)])
    reply = agent.reply("s1", "Oi")
    assert reply.degraded and reply.text == UNAVAILABLE_MESSAGE and "(67) 3321-4500" in reply.text
    assert conversations.history("s1") == []


def test_limite_de_rodadas_evita_loop_infinito(make_agent):
    agent, llm = make_agent([call("list_categories") for _ in range(MAX_TOOL_ROUNDS + 1)])
    reply = agent.reply("s1", "Oi")
    assert reply.degraded and reply.text == NO_ANSWER_MESSAGE
    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1


def test_resposta_vazia_do_modelo_vira_aviso(make_agent):
    agent, _ = make_agent([say("")])
    assert agent.reply("s1", "Oi").text == NO_ANSWER_MESSAGE


def test_entrada_longa_e_truncada(make_agent):
    agent, llm = make_agent([say("ok")])
    reply = agent.reply("s1", "a" * (MAX_INPUT_CHARS + 500))
    assert reply.input_truncated and len(llm.calls[0]["messages"][-1].text) == MAX_INPUT_CHARS


def test_mensagem_vazia_nao_chama_o_modelo(make_agent):
    agent, llm = make_agent([])
    assert agent.reply("s1", "   ").text == EMPTY_INPUT_MESSAGE and llm.calls == []


def test_session_id_obrigatorio(make_agent):
    agent, _ = make_agent([say("ok")])
    with pytest.raises(ValueError):
        agent.reply("  ", "Oi")


def test_modelo_usado_e_reportado(make_agent):
    agent, _ = make_agent([say("ok", model="gemini-reserva")])
    assert agent.reply("s1", "Oi").model == "gemini-reserva"


def test_historico_longo_e_limitado(make_agent, conversations):
    for i in range(15):
        conversations.append("s1", "user", f"pergunta {i}")
        conversations.append("s1", "assistant", f"resposta {i}")
    agent, llm = make_agent([say("ok")])
    agent.reply("s1", "nova")
    sent = llm.calls[0]["messages"]
    assert len(sent) <= 21 and sent[0].role == "user" and sent[-1].text == "nova"
