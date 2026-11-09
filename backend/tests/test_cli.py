from __future__ import annotations

from app.agent import cli
from app.agent.models import AgentReply, ToolTrace


class FakeAgent:
    def __init__(self):
        self.calls = []

    def reply(self, session, text):
        self.calls.append((session, text))
        tools = [ToolTrace("search_products", {"query": "x"}, True, "{}")]
        return AgentReply(text=f"eco: {text}", session_id=session, tools=tools)


def run_cli(monkeypatch, capsys, lines, argv=()):
    agent, received = FakeAgent(), {}

    def fake_build(**kwargs):
        received.update(kwargs)
        return agent

    monkeypatch.setattr(cli, "build_agent", fake_build)
    feed = iter(lines)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(feed))
    code = cli.main(list(argv))
    return code, agent, received, capsys.readouterr().out


def test_cli_conversa_e_encerra_com_sair(monkeypatch, capsys):
    code, agent, _, out = run_cli(monkeypatch, capsys, ["oi", "sair"], ["--session", "abc"])
    assert code == 0 and agent.calls == [("abc", "oi")]
    assert "Assistente: eco: oi" in out and "[tool]" not in out


def test_cli_passa_a_data_fixa_ao_agente(monkeypatch, capsys):
    _, _, received, _ = run_cli(monkeypatch, capsys, ["sair"], ["--now", "2025-10-28T10:00:00"])
    assert received["now"] == "2025-10-28T10:00:00"


def test_cli_mostra_ferramentas_com_a_flag_e_alterna_com_comando(monkeypatch, capsys):
    _, _, _, out = run_cli(monkeypatch, capsys, ["a", "/ferramentas", "b", "sair"], ["--show-tools"])
    assert out.count("[tool]") == 1 and "Rastro das ferramentas desligado" in out


def test_cli_nova_sessao_troca_o_session_id(monkeypatch, capsys):
    _, agent, _, out = run_cli(monkeypatch, capsys, ["a", "/nova", "b", "sair"], ["--session", "s1"])
    assert agent.calls[0][0] == "s1" and agent.calls[1][0] != "s1" and "Nova sessão" in out


def test_cli_ignora_linha_vazia_e_aceita_ctrl_d(monkeypatch, capsys):
    def lines():
        yield ""
        raise EOFError

    code, agent, _, _ = run_cli(monkeypatch, capsys, lines())
    assert code == 0 and agent.calls == []
