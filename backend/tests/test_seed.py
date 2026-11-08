import json
import sqlite3

from app.core.text import normalize
from app.database.seed import seed_database


def test_row_counts(conn):
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("categories", "products", "customers", "promotions", "orders", "order_items")
    }
    assert counts == {
        "categories": 9, "products": 65, "customers": 50,
        "promotions": 25, "orders": 20, "order_items": 22,
    }


def test_no_data_errors(conn):
    errors = conn.execute("SELECT * FROM data_quality_issues WHERE severity = 'error'").fetchall()
    assert errors == []


def test_specs_are_parsed_json(conn):
    row = conn.execute("SELECT specs_json FROM products WHERE product_id = 81").fetchone()
    specs = json.loads(row["specs_json"])
    assert specs["top"] == "Spruce"
    assert specs["strings"] == "nylon"


def test_text_normalization_has_no_accents(conn):
    row = conn.execute("SELECT name, name_norm FROM products WHERE name LIKE '%Barítono%' LIMIT 1").fetchone()
    assert "í" not in row["name_norm"]
    assert row["name_norm"] == normalize(row["name"])


def test_payment_method_is_split(conn):
    order = conn.execute("SELECT payment_type, installments FROM orders WHERE order_id = 2").fetchone()
    assert (order["payment_type"], order["installments"]) == ("credit", 6)
    pix = conn.execute("SELECT payment_type, installments FROM orders WHERE order_id = 1").fetchone()
    assert (pix["payment_type"], pix["installments"]) == ("pix", 1)


def _issues(conn, code):
    return conn.execute(
        "SELECT entity_id FROM data_quality_issues WHERE code = ? ORDER BY id", (code,)
    ).fetchall()


def test_known_inconsistencies_are_reported(conn):
    assert [r["entity_id"] for r in _issues(conn, "ACTIVE_WITHOUT_STOCK")] == ["96"]
    assert sorted(r["entity_id"] for r in _issues(conn, "ORDER_TOTAL_MISMATCH")) == ["20", "3"]
    assert sorted(r["entity_id"] for r in _issues(conn, "ORDERED_UNAVAILABLE_PRODUCT")) == ["14", "3"]
    assert [r["entity_id"] for r in _issues(conn, "DUPLICATE_EMAIL")] == ["11,43"]
    assert sorted(r["entity_id"] for r in _issues(conn, "EMPTY_CATEGORY")) == ["6", "7", "8"]
    assert sorted(r["entity_id"] for r in _issues(conn, "INSTALLMENT_BELOW_POLICY")) == ["16", "18", "9"]


def test_seed_is_idempotent(tmp_path):
    path = tmp_path / "again.db"
    first = seed_database(db_path=path)
    second = seed_database(db_path=path)
    assert first.counts == second.counts
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 65


def test_foreign_keys_hold(conn):
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
