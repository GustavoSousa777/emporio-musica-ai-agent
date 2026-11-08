"""Tratamento dos CSVs: tipos corretos, JSON de specs e colunas normalizadas."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from app.core.text import digits_only, normalize
from app.database.issues import IssueLog

_INSTALLMENT_RE = re.compile(r"^credit_(\d+)x$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _blank(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _date(value: str | None, entity: str, entity_id: object, field: str, log: IssueLog) -> str | None:
    value = _blank(value)
    if value is None:
        return None
    if not _ISO_DATE_RE.match(value):
        log.add("INVALID_DATE", "error", entity, entity_id, f"{field} fora do formato AAAA-MM-DD: {value!r}")
        return None
    return value


def clean_categories(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "category_id": int(r["category_id"]),
            "name": r["name"].strip(),
            "name_norm": normalize(r["name"]),
            "description": _blank(r.get("description")),
        }
        for r in rows
    ]


def _parse_specs(raw: str | None, product_id: int, log: IssueLog) -> dict[str, Any]:
    raw = _blank(raw)
    if raw is None:
        return {}
    try:
        specs = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.add("SPECS_INVALID_JSON", "error", "product", product_id, f"specs não é JSON válido: {exc}")
        return {}
    if not isinstance(specs, dict):
        log.add("SPECS_INVALID_JSON", "error", "product", product_id, "specs não é um objeto JSON")
        return {}
    return specs


def clean_products(
    rows: list[dict[str, str]], categories: dict[int, str], log: IssueLog
) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        pid = int(r["product_id"])
        specs = _parse_specs(r.get("specs"), pid, log)
        category_id = int(r["category_id"])
        name = r["name"].strip()
        description = _blank(r.get("description"))
        search_text = " ".join(
            part
            for part in (
                normalize(name),
                normalize(categories.get(category_id, "")),
                normalize(description),
                normalize(" ".join(str(v) for v in specs.values())),
            )
            if part
        )
        out.append(
            {
                "product_id": pid,
                "name": name,
                "name_norm": normalize(name),
                "category_id": category_id,
                "description": description,
                "price_brl": float(r["price_brl"]),
                "stock_quantity": int(r["stock_quantity"]),
                "status": r["status"].strip().lower(),
                "specs_json": json.dumps(specs, ensure_ascii=False, sort_keys=True),
                "search_text": search_text,
                "created_at": _date(r.get("created_at"), "product", pid, "created_at", log),
            }
        )
    return out


def clean_customers(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        email = _blank(r.get("email"))
        out.append(
            {
                "customer_id": int(r["customer_id"]),
                "name": r["name"].strip(),
                "phone": _blank(r.get("phone")),
                "phone_digits": digits_only(r.get("phone")) or None,
                "email": email,
                "email_norm": email.lower() if email else None,
                "city": _blank(r.get("city")),
                "city_norm": normalize(r.get("city")) or None,
            }
        )
    return out


def clean_promotions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "promotion_id": int(r["promotion_id"]),
            "product_id": int(r["product_id"]),
            "discount_percent": float(r["discount_percent"]),
            "description": _blank(r.get("description")),
            "is_active": int(r["is_active"]),
        }
        for r in rows
    ]


def clean_orders(rows: list[dict[str, str]], log: IssueLog) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        oid = int(r["order_id"])
        method = r["payment_method"].strip().lower()
        match = _INSTALLMENT_RE.match(method)
        if match:
            payment_type, installments = "credit", int(match.group(1))
        else:
            payment_type, installments = method, 1
        out.append(
            {
                "order_id": oid,
                "customer_id": int(r["customer_id"]),
                "order_date": _date(r.get("order_date"), "order", oid, "order_date", log),
                "status": r["status"].strip().lower(),
                "total_brl": float(r["total_brl"]),
                "payment_method": method,
                "payment_type": payment_type,
                "installments": installments,
                "tracking_code": _blank(r.get("tracking_code")),
                "estimated_delivery": _date(
                    r.get("estimated_delivery"), "order", oid, "estimated_delivery", log
                ),
                "notes": _blank(r.get("notes")),
            }
        )
    return out


def clean_order_items(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "order_id": int(r["order_id"]),
            "product_id": int(r["product_id"]),
            "quantity": int(r["quantity"]),
        }
        for r in rows
    ]
