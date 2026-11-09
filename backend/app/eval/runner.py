from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.agent.agent import Agent
from app.agent.memory import ConversationStore
from app.agent.models import AgentReply, LLMTurn, Message, ToolCall
from app.agent.tools import ToolContext, Toolset
from app.eval.checks import CheckResult, ToolRecord, check_expect
from app.eval.scenarios import SCENARIOS, Scenario, select

ORACLE_FINAL_TEXT = "[oráculo] resposta simulada"
PASS, FAIL, INFRA = "pass", "fail", "infra"



class RecordingToolset(Toolset):

    def __init__(self) -> None:
        super().__init__()
        self.records: list[ToolRecord] = []

    def run(self, name: str, args: dict[str, Any], ctx: ToolContext) -> tuple[dict[str, Any], bool]:
        response, ok = super().run(name, args, ctx)
        self.records.append(ToolRecord(name, dict(args or {}), response, ok))
        return response, ok


class OracleLLM:

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self._turn = 0
        self._issued = False

    def start_turn(self, index: int) -> None:
        self._turn, self._issued = index, False

    def generate(self, messages: list[Message], system: str, tools: Any) -> LLMTurn:
        calls = self.scenario.turns[self._turn].oracle
        if calls and not self._issued and messages[-1].role == "user":
            self._issued = True
            return LLMTurn(text="", tool_calls=[ToolCall(c.tool, dict(c.args)) for c in calls], model="oracle")
        return LLMTurn(text=ORACLE_FINAL_TEXT, tool_calls=[], model="oracle")


@dataclass
class ScenarioResult:
    scenario: Scenario
    status: str
    checks: list[CheckResult] = field(default_factory=list)
    replies: list[AgentReply] = field(default_factory=list)
    records: list[ToolRecord] = field(default_factory=list)
    seconds: float = 0.0
    note: str = ""

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok]



def run_scenario(
    scenario: Scenario,
    *,
    retriever,
    db_path: Path | str,
    live: bool = False,
    llm: Any = None,
) -> ScenarioResult:

    started = time.monotonic()
    oracle = None
    if llm is None:
        if live:
            raise ValueError("O modo ao vivo precisa de um LLM.")
        oracle = OracleLLM(scenario)
        llm = oracle

    with tempfile.TemporaryDirectory() as tmp:
        store = ConversationStore(Path(tmp) / "conversations.db")
        toolset = RecordingToolset()
        agent = Agent(llm, retriever, store, db_path=db_path, toolset=toolset, now=scenario.now)
        replies: list[AgentReply] = []
        for index, turn in enumerate(scenario.turns):
            if oracle is not None:
                oracle.start_turn(index)
            replies.append(agent.reply(f"eval-{scenario.id}", turn.user))
        records = list(toolset.records)

    seconds = time.monotonic() - started
    if live and any(r.degraded for r in replies):
        return ScenarioResult(
            scenario, INFRA, [], replies, records, seconds,
            note="o modelo ficou indisponível (cota ou falha de rede); não conta como falha do prompt",
        )
    checks = check_expect(
        scenario.expect, records, [r.text for r in replies], any(r.escalated for r in replies), live=live
    )
    status = PASS if all(c.ok for c in checks) else FAIL
    return ScenarioResult(scenario, status, checks, replies, records, seconds)


def run_all(
    scenarios: list[Scenario],
    *,
    retriever,
    db_path: Path | str,
    live: bool = False,
    llm: Any = None,
    pause: float = 0.0,
    on_result: Callable[[ScenarioResult], None] | None = None,
    max_infra_in_a_row: int = 2,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    infra_streak = 0
    for position, scenario in enumerate(scenarios):
        if live and position and pause:
            time.sleep(pause)
        result = run_scenario(scenario, retriever=retriever, db_path=db_path, live=live, llm=llm)
        results.append(result)
        if on_result:
            on_result(result)
        infra_streak = infra_streak + 1 if result.status == INFRA else 0
        if infra_streak >= max_infra_in_a_row:
            break  
    return results



def summarize(results: list[ScenarioResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "pass": sum(r.status == PASS for r in results),
        "fail": sum(r.status == FAIL for r in results),
        "infra": sum(r.status == INFRA for r in results),
    }


def render_report(results: list[ScenarioResult], *, live: bool, models: list[str] | None = None) -> str:
    totals = summarize(results)
    mode = "ao vivo (Gemini decide sozinho)" if live else "offline (oráculo: ferramentas e dados, sem LLM)"
    lines = [
        "# Avaliação do agente",
        "",
        f"- Modo: {mode}",
        f"- Gerado em: {datetime.now():%d/%m/%Y %H:%M}",
    ]
    if models:
        lines.append(f"- Modelos: {', '.join(models)}")
    lines += [
        f"- Resultado: **{totals['pass']} passaram**, {totals['fail']} falharam, {totals['infra']} sem resposta do modelo, de {totals['total']}",
        "",
        "| Cenário | Categoria | Resultado | Ferramentas chamadas | Tempo |",
        "|---|---|---|---|---|",
    ]
    icon = {PASS: "passou", FAIL: "**falhou**", INFRA: "sem modelo"}
    for r in results:
        tools = ", ".join(dict.fromkeys(rec.name for rec in r.records)) or "nenhuma"
        lines.append(f"| `{r.scenario.id}` | {r.scenario.category} | {icon[r.status]} | {tools} | {r.seconds:.1f}s |")

    problems = [r for r in results if r.status != PASS]
    if problems:
        lines += ["", "## Detalhes dos problemas", ""]
    for r in problems:
        lines.append(f"### `{r.scenario.id}`: {r.scenario.description}")
        if r.note:
            lines.append(f"- {r.note}")
        for check in r.failed_checks:
            detail = f" ({check.detail})" if check.detail else ""
            lines.append(f"- falhou: {check.name}{detail}")
        for turn, reply in zip(r.scenario.turns, r.replies):
            lines += ["", f"> Cliente: {turn.user}", f"> Assistente: {reply.text}"]
        lines.append("")
    skipped = [c for r in results for c in r.checks if c.skipped]
    if skipped:
        lines += ["", "_As verificações do texto da resposta só rodam com `--live`._"]
    return "\n".join(lines).rstrip() + "\n"



def _print_result(result: ScenarioResult, verbose: bool) -> None:
    mark = {PASS: "ok   ", FAIL: "FALHA", INFRA: "SEM MODELO"}[result.status]
    print(f"[{mark}] {result.scenario.id:<42} {result.seconds:5.1f}s")
    if result.status != PASS:
        if result.note:
            print(f"        {result.note}")
        for check in result.failed_checks:
            print(f"        - {check.name}" + (f" ({check.detail})" if check.detail else ""))
    if verbose or result.status == FAIL:
        for turn, reply in zip(result.scenario.turns, result.replies):
            print(f"        cliente   : {turn.user}")
            print(f"        assistente: {reply.text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia o agente em cenários com ferramenta esperada.")
    parser.add_argument("--live", action="store_true", help="usa o Gemini de verdade (precisa de GEMINI_API_KEY)")
    parser.add_argument("--core", action="store_true", help="só o subconjunto rápido")
    parser.add_argument("--id", action="append", dest="ids", help="roda só este cenário (pode repetir)")
    parser.add_argument("--category", help="roda só uma categoria")
    parser.add_argument("--pause", type=float, default=3.0, help="segundos entre cenários no modo ao vivo (padrão 3)")
    parser.add_argument("--report", help="grava o relatório em markdown neste caminho")
    parser.add_argument("--verbose", action="store_true", help="mostra as conversas também dos cenários que passaram")
    parser.add_argument("--list", action="store_true", help="lista os cenários e sai")
    args = parser.parse_args(argv)

    try:
        chosen = select(args.ids, args.category, args.core)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.list:
        for s in SCENARIOS:
            print(f"{'*' if s.core else ' '} {s.id:<42} {s.category:<20} {s.description}")
        print("\n* = subconjunto --core")
        return 0
    if not chosen:
        print("Nenhum cenário selecionado.", file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    from app.core.config import get_settings
    from app.database.connection import ensure_database
    from app.rag.retriever import Retriever, build_index, load_retriever

    settings = get_settings()
    db_path = ensure_database(settings.db_path)
    llm, models = None, None
    if args.live:
        if not settings.gemini_api_key:
            print("Defina GEMINI_API_KEY no backend/.env para usar --live.", file=sys.stderr)
            return 2
        from app.agent.gemini_llm import GeminiLLM
        from app.core.gemini_failover import ModelPool

        models = list(settings.gemini_models)
        llm = GeminiLLM(settings.gemini_api_key, ModelPool(models), thinking_level=settings.gemini_thinking_level)
        retriever = load_retriever(settings)
        print(f"Modo ao vivo. Modelos: {', '.join(models)}. Busca nas políticas: "
              f"{'híbrida' if retriever.semantic_enabled else 'só BM25'}.\n")
    else:
        retriever = Retriever(build_index(lexical_only=True), None, "lexical")
        print("Modo offline (oráculo): confere ferramentas e dados, sem LLM.\n")

    results = run_all(
        chosen, retriever=retriever, db_path=db_path, live=args.live, llm=llm, pause=args.pause,
        on_result=lambda r: _print_result(r, args.verbose),
    )
    totals = summarize(results)
    print(f"\n{totals['pass']} passaram, {totals['fail']} falharam, {totals['infra']} sem modelo, de {len(chosen)} cenários.")
    if len(results) < len(chosen):
        print(f"Interrompido após {len(results)} cenários: o modelo ficou indisponível. Rode de novo mais tarde.")
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_report(results, live=args.live, models=models), encoding="utf-8")
        print(f"Relatório salvo em {path}")
    return 0 if totals["fail"] == 0 and totals["infra"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
