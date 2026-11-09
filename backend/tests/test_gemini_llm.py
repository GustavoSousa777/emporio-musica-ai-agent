from __future__ import annotations

import pytest
from google.genai import types

from app.agent.gemini_llm import DUMMY_SIGNATURE, GeminiLLM, parse_response, to_contents, to_tools
from app.agent.models import Message, ToolCall, ToolResult
from app.agent.tools import TOOLS
from app.core.gemini_failover import LLMUnavailableError, ModelPool


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(f"erro {code}")
        self.code = code


def _response(text=None, call=None):
    parts = []
    if text:
        parts.append(types.Part.from_text(text=text))
    if call:
        parts.append(types.Part(function_call=types.FunctionCall(name=call[0], args=call[1])))
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


class FakeModels:
    def __init__(self, behaviors):
        self.behaviors = behaviors  # modelo -> lista de respostas/erros em ordem
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        item = self.behaviors[model].pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, behaviors):
        self.models = FakeModels(behaviors)


def _llm(behaviors, models=("m1", "m2")):
    return GeminiLLM(None, ModelPool(models), client=FakeClient(behaviors), sleep=lambda s: None)


# --- conversão --------------------------------------------------------------------------------
def test_to_contents_mantem_o_conteudo_original_para_o_mesmo_modelo():
    raw = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="x", args={}), thought_signature=b"sig")])
    msgs = [
        Message(role="user", text="oi"),
        Message(role="assistant", tool_calls=[ToolCall("x", {})], raw=raw, model="m1"),
        Message(role="tool", tool_results=[ToolResult("x", {"ok": True})]),
    ]
    contents = to_contents(msgs, "m1")
    assert contents[1] is raw
    assert contents[2].role == "user" and contents[2].parts[0].function_response.name == "x"


def test_to_contents_usa_assinatura_de_contorno_ao_trocar_de_modelo():
    raw = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="x", args={"a": 1}), thought_signature=b"sig")])
    msgs = [Message(role="user", text="oi"), Message(role="assistant", text="vou ver", tool_calls=[ToolCall("x", {"a": 1})], raw=raw, model="m1")]
    contents = to_contents(msgs, "m2")
    assert contents[1] is not raw
    call_part = [p for p in contents[1].parts if p.function_call][0]
    assert call_part.thought_signature == DUMMY_SIGNATURE
    assert call_part.function_call.args == {"a": 1}
    assert call_part.to_json_dict()["thought_signature"] == "skip_thought_signature_validator"


def test_to_tools_gera_declaracoes_de_todas_as_ferramentas():
    tool = to_tools(TOOLS)[0]
    names = {d.name for d in tool.function_declarations}
    assert names == {t.name for t in TOOLS} and len(names) == len(TOOLS)


def test_parse_response_separa_texto_e_chamadas():
    turn = parse_response(_response(text="Já vejo", call=("search_products", {"query": "violão"})), "m1")
    assert turn.text == "Já vejo" and turn.model == "m1"
    assert turn.tool_calls == [ToolCall("search_products", {"query": "violão"})]


def test_parse_response_sem_candidatos_devolve_vazio():
    turn = parse_response(types.GenerateContentResponse(candidates=[]), "m1")
    assert turn.text == "" and turn.tool_calls == []


# --- failover ---------------------------------------------------------------------------------
def test_generate_usa_o_primeiro_modelo():
    llm = _llm({"m1": [_response(text="oi")], "m2": []})
    turn = llm.generate([Message(role="user", text="oi")], "sys", TOOLS)
    assert turn.text == "oi" and turn.model == "m1"


def test_generate_troca_de_modelo_quando_a_cota_acaba_e_lembra_do_bloqueio():
    llm = _llm({"m1": [FakeAPIError(429)], "m2": [_response(text="a"), _response(text="b")]})
    assert llm.generate([Message(role="user", text="1")], "s", TOOLS).model == "m2"
    assert llm.generate([Message(role="user", text="2")], "s", TOOLS).model == "m2"
    assert llm._client.models.calls == ["m1", "m2", "m2"]  # m1 não é retentado enquanto bloqueado


def test_generate_tenta_de_novo_no_5xx_antes_de_trocar():
    llm = _llm({"m1": [FakeAPIError(503), _response(text="ok")], "m2": []})
    assert llm.generate([Message(role="user", text="x")], "s", TOOLS).model == "m1"


def test_generate_504_troca_de_modelo_na_hora():
    llm = _llm({"m1": [FakeAPIError(504)], "m2": [_response(text="ok")]})
    assert llm.generate([Message(role="user", text="x")], "s", TOOLS).model == "m2"
    assert llm._client.models.calls == ["m1", "m2"]  # sem segunda tentativa no m1


def test_generate_erro_400_nao_troca():
    llm = _llm({"m1": [FakeAPIError(400)], "m2": [_response(text="x")]})
    with pytest.raises(FakeAPIError):
        llm.generate([Message(role="user", text="x")], "s", TOOLS)


def test_generate_todos_sem_cota_levanta_indisponivel():
    llm = _llm({"m1": [FakeAPIError(429)], "m2": [FakeAPIError(429)]})
    with pytest.raises(LLMUnavailableError):
        llm.generate([Message(role="user", text="x")], "s", TOOLS)


def test_sem_chave_nem_cliente_falha_cedo():
    with pytest.raises(ValueError):
        GeminiLLM(None, ModelPool(["m1"]))
