from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.eval.scenarios import ArgCheck, Expect

_PRICE_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")


@dataclass
class ToolRecord:

    name: str
    args: dict[str, Any]
    response: dict[str, Any]
    ok: bool


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False


def fold(text: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def extract_prices(text: str) -> list[float]:
    prices = []
    for raw in _PRICE_RE.findall(text or ""):
        prices.append(float(raw.replace(".", "").replace(",", ".")))
    return prices


def results_text(records: list[ToolRecord]) -> str:
    return fold(" ".join(json.dumps(r.response, ensure_ascii=False, default=str) for r in records))


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _arg_matches(check: ArgCheck, value: Any) -> bool:
    if value is None:
        return False
    if check.op == "eq":
        a, b = _as_number(value), _as_number(check.value)
        if a is not None and b is not None:
            return abs(a - b) < 1e-9
        return fold(str(value)).strip() == fold(str(check.value)).strip()
    if check.op == "contains":
        return fold(str(check.value)) in fold(str(value))
    if check.op == "approx":
        a, b = _as_number(value), _as_number(check.value)
        return a is not None and b is not None and abs(a - b) <= abs(b) * 0.01
    if check.op == "between":
        number = _as_number(value)
        low, high = check.value
        return number is not None and low <= number <= high
    raise ValueError(f"Operador de argumento desconhecido: {check.op}")


def _describe(check: ArgCheck) -> str:
    return f"{check.tool}.{check.arg} {check.op} {check.value!r}"


def check_tools(expect: Expect, records: list[ToolRecord]) -> list[CheckResult]:
    used = [r.name for r in records]
    results: list[CheckResult] = []
    if expect.no_tools:
        results.append(CheckResult("nenhuma ferramenta", not used, f"chamou: {sorted(set(used))}" if used else ""))
    for name in expect.tools_all:
        results.append(CheckResult(f"chamou {name}", name in used, "" if name in used else f"chamou: {sorted(set(used))}"))
    if expect.tools_any:
        ok = any(name in used for name in expect.tools_any)
        results.append(CheckResult(f"chamou alguma de {list(expect.tools_any)}", ok, "" if ok else f"chamou: {sorted(set(used))}"))
    for name in expect.tools_none:
        results.append(CheckResult(f"não chamou {name}", name not in used, "chamou indevidamente" if name in used else ""))
    for check in expect.args:
        values = [r.args.get(check.arg) for r in records if r.name == check.tool]
        ok = any(_arg_matches(check, v) for v in values)
        results.append(CheckResult(f"argumento {_describe(check)}", ok, "" if ok else f"valores recebidos: {values}"))
    return results


def check_results(expect: Expect, records: list[ToolRecord]) -> list[CheckResult]:
    blob = results_text(records)
    results = []
    for snippet in expect.results_contain:
        ok = fold(snippet) in blob
        results.append(CheckResult(f"resultado contém {snippet!r}", ok, "" if ok else "trecho ausente nos resultados das ferramentas"))
    return results


def check_replies(expect: Expect, reply_texts: list[str], escalated: bool) -> list[CheckResult]:
    text = fold(" ".join(reply_texts) if expect.scope == "all" else (reply_texts[-1] if reply_texts else ""))
    results: list[CheckResult] = []
    for pattern in expect.reply_all:
        ok = re.search(pattern, text) is not None
        results.append(CheckResult(f"resposta contém /{pattern}/", ok, "" if ok else "padrão ausente"))
    for group in expect.reply_any:
        ok = any(re.search(p, text) for p in group)
        label = " | ".join(group[:4]) + (" | ..." if len(group) > 4 else "")
        results.append(CheckResult(f"resposta contém um de: {label}", ok, "" if ok else "nenhum padrão do grupo apareceu"))
    for pattern in expect.reply_none:
        found = re.search(pattern, text)
        results.append(CheckResult(f"resposta NÃO contém /{pattern}/", found is None, f"apareceu: {found.group(0)!r}" if found else ""))
    if expect.reply_prices_max is not None:
        prices = extract_prices(text if expect.scope == "all" else " ".join(reply_texts[-1:]))
        over = [p for p in prices if p > expect.reply_prices_max]
        results.append(CheckResult(f"preços citados <= R$ {expect.reply_prices_max:g}", not over, f"acima do limite: {over}" if over else ""))
    if expect.escalated is not None:
        results.append(CheckResult(
            f"encaminhado à equipe = {expect.escalated}", escalated == expect.escalated,
            f"escalated={escalated}" if escalated != expect.escalated else "",
        ))
    return results


def skipped_reply_checks(expect: Expect) -> list[CheckResult]:
    count = len(expect.reply_all) + len(expect.reply_any) + len(expect.reply_none) + (1 if expect.reply_prices_max is not None else 0)
    if count == 0:
        return []
    return [CheckResult(f"{count} verificação(ões) de texto da resposta", True, "só no modo --live", skipped=True)]


def check_expect(expect: Expect, records: list[ToolRecord], reply_texts: list[str], escalated: bool, live: bool) -> list[CheckResult]:
    results = check_tools(expect, records) + check_results(expect, records)
    if live:
        results += check_replies(expect, reply_texts, escalated)
    else:
        if expect.escalated is not None:
            results.append(CheckResult(
                f"encaminhado à equipe = {expect.escalated}", escalated == expect.escalated,
                f"escalated={escalated}" if escalated != expect.escalated else "",
            ))
        results += skipped_reply_checks(expect)
    return results
