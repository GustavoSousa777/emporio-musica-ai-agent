from __future__ import annotations

import http.server
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.agent.agent import MAX_INPUT_CHARS, UNAVAILABLE_MESSAGE, Agent
from app.agent.models import LLMTurn, ToolCall
from app.api.ratelimit import RateLimiter
from app.core.config import get_settings
from app.core.gemini_failover import LLMUnavailableError
from app.healthcheck import main as healthcheck_main
from app.main import create_app


class ScriptedLLM:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def generate(self, messages, system, tools):
        self.calls.append(list(messages))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def say(text, model="m1"):
    return LLMTurn(text=text, tool_calls=[], model=model)


def call(name, **args):
    return LLMTurn(text="", tool_calls=[ToolCall(name, args)], model="m1")


@pytest.fixture()
def make_client(db_path, retriever, conversations):
    clients = []

    def factory(turns=(), **overrides):
        llm = ScriptedLLM(turns)
        agent = Agent(llm, retriever, conversations, db_path=db_path, now="2026-03-23T10:00:00")
        settings = replace(get_settings(), gemini_api_key=None, **{"rate_limit_per_minute": 0, **overrides})
        client = TestClient(create_app(agent, settings))
        client.__enter__()
        clients.append(client)
        return client, llm

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def test_chat_devolve_resposta_e_gera_session_id(make_client):
    client, _ = make_client([say("Oi! Como posso ajudar?")])
    response = client.post("/chat", json={"message": "Oi"})
    body = response.json()
    assert response.status_code == 200
    assert body["reply"] == "Oi! Como posso ajudar?"
    assert len(body["session_id"]) == 32 and body["tools"] == []
    assert body["escalated"] is False and body["degraded"] is False and body["model"] == "m1"


def test_mesma_sessao_mantem_o_historico(make_client):
    client, llm = make_client([say("Olá!"), say("Sobre o pedido 8, claro.")])
    first = client.post("/chat", json={"message": "Quero saber do pedido 8"}).json()
    client.post("/chat", json={"message": "É o do violão", "session_id": first["session_id"]})
    assert [m.text for m in llm.calls[1]] == ["Quero saber do pedido 8", "Olá!", "É o do violão"]


def test_sessoes_diferentes_nao_se_misturam(make_client):
    client, llm = make_client([say("a"), say("b")])
    client.post("/chat", json={"message": "primeira", "session_id": "s1"})
    client.post("/chat", json={"message": "segunda", "session_id": "s2"})
    assert [m.text for m in llm.calls[1]] == ["segunda"]


def test_resposta_traz_so_nome_e_status_das_ferramentas(make_client):
    client, _ = make_client([
        call("get_order_status", order_id=1, email="pedro.oliveira@jmail.com"),
        say("Seu pedido foi entregue."),
    ])
    body = client.post("/chat", json={"message": "Cadê o pedido 1? pedro.oliveira@jmail.com"}).json()
    assert body["tools"] == [{"name": "get_order_status", "ok": True}]
    assert "pedro.oliveira" not in str(body["tools"])


def test_escalonamento_aparece_na_resposta(make_client):
    client, _ = make_client([
        call("escalate_to_human", reason="human_requested", summary="Cliente pediu um atendente."),
        say("Registrei. Protocolo ATD-00001."),
    ])
    assert client.post("/chat", json={"message": "Quero um atendente"}).json()["escalated"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": ""},
        {"message": "   "},
        {"message": "a" * (MAX_INPUT_CHARS + 1)},
        {"message": "oi", "session_id": "com espaço"},
        {"message": "oi", "session_id": "x" * 65},
        {"message": "oi", "session_id": "../etc"},
        {"message": 123},
    ],
)
def test_entrada_invalida_devolve_422_sem_chamar_o_modelo(make_client, payload):
    client, llm = make_client([])
    assert client.post("/chat", json=payload).status_code == 422
    assert llm.calls == []


def test_mensagem_no_limite_e_aceita(make_client):
    client, _ = make_client([say("ok")])
    assert client.post("/chat", json={"message": "a" * MAX_INPUT_CHARS}).status_code == 200


def test_modelo_indisponivel_devolve_200_com_aviso(make_client):
    client, _ = make_client([LLMUnavailableError("sem cota", wait_seconds=3600, daily_quota=True)])
    response = client.post("/chat", json={"message": "Oi"})
    assert response.status_code == 200
    assert response.json()["degraded"] is True and response.json()["reply"] == UNAVAILABLE_MESSAGE


def test_erro_inesperado_vira_500_sem_vazar_detalhes():
    class Broken:
        db_path = None
        retriever = None

        def reply(self, session_id, text):
            raise RuntimeError("segredo interno")

    app = create_app(Broken(), replace(get_settings(), rate_limit_per_minute=0))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/chat", json={"message": "Oi"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno. Tente de novo em instantes."}


def test_chave_de_api_exigida_quando_configurada(make_client):
    client, _ = make_client([say("ok")], api_key="segredo")
    assert client.post("/chat", json={"message": "Oi"}).status_code == 401
    assert client.post("/chat", json={"message": "Oi"}, headers={"X-API-Key": "errada"}).status_code == 401
    assert client.post("/chat", json={"message": "Oi"}, headers={"X-API-Key": "segredo"}).status_code == 200
    assert client.get("/health").status_code == 200


def test_limite_de_taxa_devolve_429_com_retry_after(make_client):
    client, _ = make_client([say("a"), say("b")], rate_limit_per_minute=2)
    assert client.post("/chat", json={"message": "1"}).status_code == 200
    assert client.post("/chat", json={"message": "2"}).status_code == 200
    blocked = client.post("/chat", json={"message": "3"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) >= 1


def test_limite_de_taxa_e_por_ip_atras_de_proxy(make_client):
    client, _ = make_client([say("a"), say("b")], rate_limit_per_minute=1, trust_proxy=True)
    first = client.post("/chat", json={"message": "1"}, headers={"X-Forwarded-For": "10.0.0.1, 172.16.0.1"})
    other = client.post("/chat", json={"message": "2"}, headers={"X-Forwarded-For": "10.0.0.2"})
    again = client.post("/chat", json={"message": "3"}, headers={"X-Forwarded-For": "10.0.0.1"})
    assert (first.status_code, other.status_code, again.status_code) == (200, 200, 429)


def test_requisicao_invalida_nao_gasta_o_limite(make_client):
    client, _ = make_client([say("ok")], rate_limit_per_minute=1)
    for _ in range(3):
        assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={"message": "oi"}).status_code == 200


def test_cors_libera_so_as_origens_configuradas(make_client):
    client, _ = make_client([], cors_origins=("http://localhost:3000",))
    ok = client.options(
        "/chat", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    )
    blocked = client.options(
        "/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked.headers


def test_health_ok(make_client):
    client, _ = make_client([])
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok" and body["ready"] is True and body["database"] is True
    assert body["rag"]["chunks"] >= 20 and body["rag"]["mode"] == "lexical"
    assert body["llm"]["key_configured"] is False and body["llm"]["models"]
    assert "api_key" not in str(body).lower()


def test_health_degradado_quando_o_banco_nao_existe(retriever, conversations, tmp_path):
    agent = Agent(ScriptedLLM([]), retriever, conversations, db_path=tmp_path / "vazio.db")
    with TestClient(create_app(agent, get_settings())) as client:
        response = client.get("/health")
    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "degraded" and body["database"] is False and body["detail"]


def test_sem_agente_o_health_explica_e_o_chat_devolve_503(monkeypatch):
    def broken(settings):
        raise ValueError("Defina GEMINI_API_KEY no backend/.env para usar o agente.")

    monkeypatch.setattr("app.main.build_agent", broken)
    with TestClient(create_app(settings=replace(get_settings(), rate_limit_per_minute=0))) as client:
        health = client.get("/health")
        chat = client.post("/chat", json={"message": "Oi"})
    assert health.status_code == 503 and health.json()["ready"] is False
    assert "GEMINI_API_KEY" in health.json()["detail"]
    assert chat.status_code == 503


def test_documentacao_openapi_lista_as_rotas(make_client):
    client, _ = make_client([])
    paths = client.get("/openapi.json").json()["paths"]
    assert "/chat" in paths and "/health" in paths


def test_rate_limiter_janela_deslizante():
    now = [0.0]
    limiter = RateLimiter(2, window=60, clock=lambda: now[0])
    assert limiter.check("a") is None and limiter.check("a") is None
    assert limiter.check("a") == 60
    assert limiter.check("b") is None
    now[0] = 61
    assert limiter.check("a") is None


def test_rate_limiter_zero_desliga():
    limiter = RateLimiter(0)
    assert all(limiter.check("a") is None for _ in range(100))


def test_rate_limiter_descarta_chaves_antigas(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("app.api.ratelimit.PRUNE_AT", 3)
    limiter = RateLimiter(5, window=10, clock=lambda: now[0])
    for key in "abcd":
        limiter.check(key)
    now[0] = 100
    limiter.check("novo")
    assert set(limiter._hits) == {"novo"}


def _serve(status):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.parametrize("status, expected", [(200, 0), (503, 1)])
def test_healthcheck_do_docker_usa_o_status_do_health(monkeypatch, status, expected):
    server = _serve(status)
    monkeypatch.setenv("PORT", str(server.server_address[1]))
    try:
        assert healthcheck_main() == expected
    finally:
        server.shutdown()


def test_healthcheck_do_docker_falha_sem_servidor(monkeypatch):
    monkeypatch.setenv("PORT", "1")
    assert healthcheck_main() == 1
