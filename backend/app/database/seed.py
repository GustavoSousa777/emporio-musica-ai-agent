"""Ingestão dos CSVs no SQLite, com tratamento e validação.

Uso (a partir de backend/):
    python -m app.database.seed
    python -m app.database.seed --db data/emporio.db --report ../docs/data_quality.md
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.core.config import RAW_DATA_DIR, REPO_DIR, get_settings
from app.database import cleaning
from app.database.issues import IssueLog
from app.database.validation import run_validations

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_REPORT = REPO_DIR / "docs" / "data_quality.md"

_INSERTS = {
    "categories": ("category_id", "name", "name_norm", "description"),
    "products": (
        "product_id", "name", "name_norm", "category_id", "description", "price_brl",
        "stock_quantity", "status", "specs_json", "search_text", "created_at",
    ),
    "customers": (
        "customer_id", "name", "phone", "phone_digits", "email", "email_norm", "city", "city_norm",
    ),
    "promotions": ("promotion_id", "product_id", "discount_percent", "description", "is_active"),
    "orders": (
        "order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
        "payment_type", "installments", "tracking_code", "estimated_delivery", "notes",
    ),
    "order_items": ("order_id", "product_id", "quantity"),
}


class DataValidationError(RuntimeError):
    """Levantada quando os dados têm erros (não apenas avisos)."""


@dataclass
class SeedSummary:
    db_path: Path
    counts: dict[str, int]
    issues: IssueLog


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    cols = _INSERTS[table]
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])


def seed_database(
    raw_dir: Path | str | None = None,
    db_path: Path | str | None = None,
    report_path: Path | str | None = None,
    strict: bool = True,
) -> SeedSummary:
    raw = Path(raw_dir) if raw_dir else RAW_DATA_DIR
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)

    log = IssueLog()
    categories = cleaning.clean_categories(cleaning.read_csv(raw / "categories.csv"))
    category_names = {c["category_id"]: c["name"] for c in categories}
    products = cleaning.clean_products(cleaning.read_csv(raw / "products.csv"), category_names, log)
    customers = cleaning.clean_customers(cleaning.read_csv(raw / "customers.csv"))
    promotions = cleaning.clean_promotions(cleaning.read_csv(raw / "promotions.csv"))
    orders = cleaning.clean_orders(cleaning.read_csv(raw / "orders.csv"), log)
    items = cleaning.clean_order_items(cleaning.read_csv(raw / "order_items.csv"))

    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # FKs desligadas na carga: as violações são reportadas pela validação.
        conn.execute("PRAGMA foreign_keys = OFF")
        _insert(conn, "categories", categories)
        _insert(conn, "products", products)
        _insert(conn, "customers", customers)
        _insert(conn, "promotions", promotions)
        _insert(conn, "orders", orders)
        _insert(conn, "order_items", items)
        conn.commit()

        run_validations(conn, log)
        conn.executemany(
            "INSERT INTO data_quality_issues (code, severity, entity, entity_id, message) VALUES (?,?,?,?,?)",
            [(i.code, i.severity, i.entity, i.entity_id, i.message) for i in log.issues],
        )
        conn.commit()
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _INSERTS
        }
    finally:
        conn.close()

    summary = SeedSummary(db_path=path, counts=counts, issues=log)
    if report_path is not None:
        write_report(summary, Path(report_path))
    if strict and log.has_errors():
        raise DataValidationError(
            "Erros nos dados:\n" + "\n".join(f"- {i.code}: {i.message}" for i in log.by_severity("error"))
        )
    return summary


_SEVERITY_LABEL = {"error": "Erro", "warning": "Aviso", "info": "Informação"}


def write_report(summary: SeedSummary, path: Path) -> None:
    """Gera docs/data_quality.md a partir das inconsistências detectadas."""
    lines = [
        "# Qualidade dos dados",
        "",
        "Relatório gerado automaticamente por `python -m app.database.seed`.",
        "Não edite à mão; as decisões de negócio sobre cada ponto estão em [premissas.md](premissas.md).",
        "",
        "## Volume carregado",
        "",
        "| Tabela | Linhas |",
        "|---|---|",
    ]
    lines += [f"| {t} | {n} |" for t, n in summary.counts.items()]

    totals = Counter(i.severity for i in summary.issues.issues)
    lines += [
        "",
        "## Resumo",
        "",
        f"- Erros: {totals.get('error', 0)}",
        f"- Avisos: {totals.get('warning', 0)}",
        f"- Informações: {totals.get('info', 0)}",
        "",
        "## Inconsistências detectadas",
    ]
    grouped: dict[str, list] = {}
    for issue in summary.issues.issues:
        grouped.setdefault(issue.code, []).append(issue)
    for code, issues in sorted(grouped.items(), key=lambda kv: (kv[1][0].severity, kv[0])):
        lines += ["", f"### {code} ({_SEVERITY_LABEL[issues[0].severity]}, {len(issues)})", ""]
        lines += [f"- {i.entity} {i.entity_id}: {i.message}" for i in issues]
    lines += [
        "",
        "## Inconsistências do manual de políticas (PDF)",
        "",
        "Não são detectáveis pelo seed; foram encontradas na leitura e tratadas em `app/core/rules.py`.",
        "",
        "- Telefone: capa e seção 1.2 informam (67) 3341-4444; a seção 7 cita o WhatsApp (67) 3321-4500.",
        "- E-mail: a seção 1.2 grafa `empóriodamusica` com acento; a capa grafa sem acento.",
        "- Parcelamento: a tabela da seção 3 fala em parcela mínima de R$ 100 para todo o crédito; "
        "a seção 3.1 define faixas (3x sem mínimo, 4x a 6x com R$ 80, 7x a 12x com R$ 100).",
        "- Catálogo: o manual cita \"mais de 300 instrumentos\" e sopros/cordas orquestrais; a base tem "
        "65 produtos e nenhum de sopro ou cordas orquestrais.",
        "- Garantia: 4.2 fala em troca por defeito em 30 dias; 8.1 fala em garantia legal de 90 dias.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carrega os CSVs no SQLite.")
    parser.add_argument("--raw", type=Path, default=RAW_DATA_DIR, help="pasta dos CSVs")
    parser.add_argument("--db", type=Path, default=None, help="caminho do SQLite")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="relatório de qualidade (.md)")
    parser.add_argument("--no-strict", action="store_true", help="não aborta em erros de dados")
    args = parser.parse_args(argv)

    try:
        summary = seed_database(args.raw, args.db, args.report, strict=not args.no_strict)
    except DataValidationError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Banco criado em {summary.db_path}")
    for table, n in summary.counts.items():
        print(f"  {table:<12} {n}")
    totals = Counter(i.severity for i in summary.issues.issues)
    print(
        f"Qualidade: {totals.get('error', 0)} erros, {totals.get('warning', 0)} avisos, "
        f"{totals.get('info', 0)} infos. Relatório: {args.report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
