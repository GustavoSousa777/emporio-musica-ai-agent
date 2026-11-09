"""Avaliação do agente: cenários bem formados, oráculo sobre os dados reais e verificadores."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.agent.models import LLMTurn, ToolCall
from app.agent.tools import TOOLS
from app.core.gemini_failover import LLMUnavailableError
from app.eval import checks
from app.eval.checks import ToolRecord, check_replies, check_tools, extract_prices, fold
from app.eval.runner import FAIL, INFRA, PASS, render_report, run_all, run_scenario, summarize
from app.eval.scenarios import CATEGORIES, SCENARIOS, SCENARIOS_BY_ID, A, Call, Expect, Scenario, T, select

TOOL_NAMES = {t.name for t in TOOLS}


# --- cenários -------------------------------------------------------------------------------
def test_conjunto_de_cenarios_tem_o_tamanho_pedido():
    assert 20 <= len(SCENARIOS) <= 30
    assert len({s.id for s in SCENARIOS}) == len(SCENARIOS)


def test_todas_as_categorias_estao_cobertas():
    assert {s.category for s in SCENARIOS} == set(CATEGORIES)


def test_subconjunto_core_cobre_varias_categorias():
    core = select(core=True)
    assert 8 <= len(core) < len(SCENARIOS)
    assert len({s.category for s in core}) >= 6


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_cenario_bem_formado(scenario):
    assert scenario.turns and all(t.user.strip() for t in scenario.turns)
    for turn in scenario.turns:
        for call in turn.oracle:
            assert call.tool in TOOL_NAMES, f"{scenario.id}: ferramenta inexistente {call.tool}"
    e = scenario.expect
    has_check = e.tools_all or e.tools_any or e.tools_none or e.no_tools or e.args or e.results_contain \
        or e.reply_all or e.reply_any or e.reply_none or e.reply_prices_max is not None or e.escalated is not None
    assert has_check, f"{scenario.id} não confere nada"
    for name in (*e.tools_all, *e.tools_any, *e.tools_none):
        assert name in TOOL_NAMES


def test_select_filtra_e_rejeita_id_desconhecido():
    assert [s.id for s in select(["loja_endereco"])] == ["loja_endereco"]
    assert {s.category for s in select(category="loja")} == {"loja"}
    with pytest.raises(KeyError):
        select(["nao_existe"])


# --- oráculo: os dados reais sustentam cada cenário -------------------------------------------
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_oraculo_passa_em_todos_os_cenarios(scenario, retriever, db_path):
    result = run_scenario(scenario, retriever=retriever, db_path=db_path)
    assert result.status == PASS, [f"{c.name} ({c.detail})" for c in result.failed_checks]


def test_oraculo_marca_as_verificacoes_de_texto_como_so_ao_vivo(retriever, db_path):
    result = run_scenario(SCENARIOS_BY_ID["catalogo_preco_takamine_gd20"], retriever=retriever, db_path=db_path)
    assert any(c.skipped for c in result.checks)


def test_cenarios_nao_compartilham_historico_nem_protocolos(retriever, db_path):
    first = run_scenario(SCENARIOS_BY_ID["escalonamento_pedir_atendente"], retriever=retriever, db_path=db_path)
    again = run_scenario(SCENARIOS_BY_ID["escalonamento_pedir_atendente"], retriever=retriever, db_path=db_path)
    protocols = [r.response["protocol"] for res in (first, again) for r in res.records if r.name == "escalate_to_human"]
    assert protocols == ["ATD-00001", "ATD-00001"]


# --- verificadores --------------------------------------------------------------------------------
def test_fold_remove_acento_e_caixa():
    assert fold("Não é Cumulativo, Ação") == "nao e cumulativo, acao"


def test_extract_prices():
    assert extract_prices("De R$ 5.999,00 por R$5.519,08 ou R$ 85 e R$1000") == [5999.0, 5519.08, 85.0, 1000.0]
    assert extract_prices("sem preço") == []


def rec(name, **args):
    return ToolRecord(name, args, {}, True)


def test_check_tools_all_any_none():
    expect = Expect(tools_all=("a",), tools_any=("b", "c"), tools_none=("d",))
    ok = check_tools(expect, [rec("a"), rec("c")])
    assert all(c.ok for c in ok)
    bad = check_tools(expect, [rec("a"), rec("d")])
    assert [c.ok for c in bad] == [True, False, False]


def test_check_tools_no_tools():
    assert check_tools(Expect(no_tools=True), [])[0].ok
    assert not check_tools(Expect(no_tools=True), [rec("a")])[0].ok


@pytest.mark.parametrize(
    "check,value,expected",
    [
        (A("t", "max_price", "eq", 1000), 1000, True),
        (A("t", "max_price", "eq", 1000), "1000", True),
        (A("t", "max_price", "eq", 1000), 999, False),
        (A("t", "reason", "eq", "arrependimento"), "Arrependimento", True),
        (A("t", "category", "contains", "viol"), "Violões", True),
        (A("t", "amount", "approx", 2199), 2199.5, True),
        (A("t", "amount", "approx", 2199), 2500, False),
        (A("t", "max_price", "between", (750, 900)), 800, True),
        (A("t", "max_price", "between", (750, 900)), 1000, False),
        (A("t", "x", "eq", 1), None, False),
    ],
)
def test_operadores_de_argumento(check, value, expected):
    result = check_tools(Expect(args=(check,)), [rec("t", **{check.arg: value})])[0]
    assert result.ok is expected


def test_argumento_de_outra_ferramenta_nao_conta():
    check = A("t", "x", "eq", 1)
    assert not check_tools(Expect(args=(check,)), [rec("outra", x=1)])[0].ok


def test_resultados_das_ferramentas_sao_buscados_sem_acento():
    records = [ToolRecord("t", {}, {"summary": "O desconto do PIX não é cumulativo"}, True)]
    assert checks.check_results(Expect(results_contain=("nao e cumulativo",)), records)[0].ok
    assert not checks.check_results(Expect(results_contain=("outra coisa",)), records)[0].ok


def test_check_replies_padroes_e_grupos():
    expect = Expect(reply_all=(r"2\.?199",), reply_any=(("indispon", "esgotad"),), reply_none=(r"1\.?935",))
    assert all(c.ok for c in check_replies(expect, ["O Takamine custa R$ 2.199,00 e está indisponível."], False))
    bad = check_replies(expect, ["Com 12% de desconto fica R$ 1.935,12"], False)
    assert [c.ok for c in bad] == [False, False, False]


def test_check_replies_limite_de_preco():
    expect = Expect(reply_prices_max=1000)
    assert check_replies(expect, ["Temos por R$ 429,90 e R$ 999,00"], False)[0].ok
    assert not check_replies(expect, ["Também tem a Taylor por R$ 5.999,00"], False)[0].ok


def test_check_replies_escopo_ultima_ou_todas():
    last = Expect(reply_all=(r"atd-\d{5}",))
    every = Expect(reply_all=(r"atd-\d{5}",), scope="all")
    texts = ["Protocolo ATD-00001", "Algo mais?"]
    assert not check_replies(last, texts, False)[0].ok
    assert check_replies(every, texts, False)[0].ok


def test_check_replies_escalonamento():
    expect = Expect(escalated=True)
    assert check_replies(expect, ["ok"], True)[0].ok
    assert not check_replies(expect, ["ok"], False)[0].ok


# --- modo ao vivo (com LLM injetado, sem rede) ------------------------------------------------------
class FakeLLM:
    def __init__(self, turns):
        self.turns = list(turns)

    def generate(self, messages, system, tools):
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def say(text):
    return LLMTurn(text=text, tool_calls=[], model="fake")


def call(name, **args):
    return LLMTurn(text="", tool_calls=[ToolCall(name, args)], model="fake")


def test_ao_vivo_passa_com_boa_resposta(retriever, db_path):
    llm = FakeLLM([call("search_products", query="Takamine GD20"), say("O Takamine GD20 custa R$ 2.199,00.")])
    result = run_scenario(SCENARIOS_BY_ID["catalogo_preco_takamine_gd20"], retriever=retriever, db_path=db_path, live=True, llm=llm)
    assert result.status == PASS and not any(c.skipped for c in result.checks)


def test_ao_vivo_falha_com_preco_inventado(retriever, db_path):
    llm = FakeLLM([call("search_products", query="Takamine GD20"), say("O Takamine GD20 sai por R$ 1.935,00 hoje.")])
    result = run_scenario(SCENARIOS_BY_ID["catalogo_preco_takamine_gd20"], retriever=retriever, db_path=db_path, live=True, llm=llm)
    assert result.status == FAIL
    assert any("2" in c.name for c in result.failed_checks)


def test_ao_vivo_falha_quando_nao_consulta_a_ferramenta(retriever, db_path):
    llm = FakeLLM([say("O Takamine GD20 custa R$ 2.199,00.")])
    result = run_scenario(SCENARIOS_BY_ID["catalogo_preco_takamine_gd20"], retriever=retriever, db_path=db_path, live=True, llm=llm)
    assert result.status == FAIL
    assert any(c.name == "chamou search_products" for c in result.failed_checks)


def test_ao_vivo_modelo_indisponivel_nao_conta_como_falha_do_prompt(retriever, db_path):
    llm = FakeLLM([LLMUnavailableError("sem cota", daily_quota=True)])
    result = run_scenario(SCENARIOS_BY_ID["loja_endereco"], retriever=retriever, db_path=db_path, live=True, llm=llm)
    assert result.status == INFRA and result.note


def test_run_all_para_depois_de_duas_indisponibilidades_seguidas(retriever, db_path):
    llm = FakeLLM([LLMUnavailableError("sem cota") for _ in range(10)])
    scenarios = select(core=True)
    results = run_all(scenarios, retriever=retriever, db_path=db_path, live=True, llm=llm)
    assert len(results) == 2 and all(r.status == INFRA for r in results)


def test_ao_vivo_exige_llm(retriever, db_path):
    with pytest.raises(ValueError):
        run_scenario(SCENARIOS[0], retriever=retriever, db_path=db_path, live=True)


def test_cenario_que_o_oraculo_nao_sustenta_falha(retriever, db_path):
    scenario = Scenario(
        "x", "loja", "teste", (T("Qual o endereço?", Call("get_store_info")),),
        Expect(tools_all=("search_products",), results_contain=("inexistente",)),
    )
    result = run_scenario(scenario, retriever=retriever, db_path=db_path)
    assert result.status == FAIL and len(result.failed_checks) == 2


# --- relatório e linha de comando ---------------------------------------------------------------------
def test_relatorio_lista_cenarios_e_detalha_falhas(retriever, db_path):
    ok = run_scenario(SCENARIOS_BY_ID["loja_endereco"], retriever=retriever, db_path=db_path)
    bad_scenario = replace(SCENARIOS_BY_ID["loja_endereco"], id="loja_endereco_ruim", expect=Expect(tools_all=("search_products",)))
    bad = run_scenario(bad_scenario, retriever=retriever, db_path=db_path)
    report = render_report([ok, bad], live=False)
    assert "| `loja_endereco` |" in report and "**falhou**" in report
    assert "Detalhes dos problemas" in report and "chamou search_products" in report
    assert "só rodam com `--live`" in report
    assert summarize([ok, bad]) == {"total": 2, "pass": 1, "fail": 1, "infra": 0}


@pytest.fixture()
def eval_env(monkeypatch, tmp_path, db_path):
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    return tmp_path


def test_main_offline_roda_e_grava_relatorio(eval_env, capsys):
    from app.eval.runner import main

    report = eval_env / "docs" / "avaliacao_offline.md"
    code = main(["--id", "loja_endereco", "--id", "frete_outra_cidade", "--report", str(report)])
    out = capsys.readouterr().out
    assert code == 0 and "2 passaram, 0 falharam" in out
    assert report.exists() and "Avaliação do agente" in report.read_text(encoding="utf-8")


def test_main_lista_cenarios(capsys):
    from app.eval.runner import main

    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "catalogo_preco_takamine_gd20" in out and "subconjunto --core" in out


def test_main_id_desconhecido_e_ao_vivo_sem_chave(eval_env, capsys):
    from app.eval.runner import main

    assert main(["--id", "nao_existe"]) == 2
    assert main(["--live", "--core"]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err
