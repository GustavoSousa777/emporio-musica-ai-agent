"""Regras de devolução, troca e garantia.

Pedido 1: comprado em 2025-10-15, entrega prevista (referência de recebimento) 2025-10-25.
"""
import pytest

from app.services.returns import check_return_eligibility

EMAIL = "pedro.oliveira@jmail.com"


def check(conn, reason, now, order_id=1, email=EMAIL):
    return check_return_eligibility(conn, order_id, reason, email=email, now=now)


def test_regret_within_seven_days(conn):
    r = check(conn, "arrependimento", "2025-10-28")
    assert r.outcome == "eligible" and r.eligible is True
    assert r.days_elapsed == 3
    assert r.deadline == "2025-11-01"
    assert r.rule == "4.1"
    assert any("10 dias úteis" in c for c in r.conditions)
    assert any("frete de devolução" in c for c in r.conditions)
    assert any("data prevista de entrega" in a for a in r.assumptions)


def test_regret_on_last_day_still_eligible(conn):
    assert check(conn, "arrependimento", "2025-11-01").eligible is True


def test_regret_one_day_late_is_not_eligible_but_points_to_warranty(conn):
    r = check(conn, "arrependimento", "2025-11-02")
    assert r.outcome == "not_eligible" and r.eligible is False
    assert r.days_elapsed == 8
    assert any("garantia legal" in s for s in r.next_steps)


def test_regret_long_after_has_no_warranty_hint(conn):
    r = check(conn, "arrependimento", "2026-03-23")
    assert r.outcome == "not_eligible"
    assert r.next_steps == []


def test_preference_swap_within_window(conn):
    r = check(conn, "preferencia", "2025-10-30")
    assert r.outcome == "eligible" and r.rule == "4.3"
    assert any("disponibilidade" in c for c in r.conditions)


def test_defect_within_30_days_of_purchase(conn):
    r = check(conn, "defeito", "2025-11-10")
    assert r.outcome == "eligible" and r.rule == "4.2"
    assert r.deadline == "2025-11-14"


def test_defect_after_30_days_falls_back_to_legal_warranty(conn):
    r = check(conn, "defeito", "2025-11-20")
    assert r.outcome == "legal_warranty" and r.eligible is None
    assert r.deadline == "2026-01-23"  # 2025-10-25 + 90 dias
    assert any("fabricante" in s for s in r.next_steps)


def test_defect_after_legal_warranty_only_manufacturer_remains(conn):
    r = check(conn, "defeito", "2026-03-23")
    assert r.outcome == "manufacturer_warranty"
    assert "certificado" in r.summary


def test_order_not_yet_delivered(conn):
    email = conn.execute("SELECT email FROM customers WHERE customer_id = 8").fetchone()["email"]
    r = check(conn, "arrependimento", "2026-03-23", order_id=13, email=email)
    assert r.outcome == "not_delivered"
    assert any("atendimento humano" in s for s in r.next_steps)


def test_cancelled_order(conn):
    email = conn.execute("SELECT email FROM customers WHERE customer_id = 15").fetchone()["email"]
    r = check(conn, "arrependimento", "2026-03-23", order_id=17, email=email)
    assert r.outcome == "cancelled_order" and r.eligible is False


def test_requires_verification(conn):
    r = check_return_eligibility(conn, 1, "arrependimento", now="2025-10-28")
    assert r.outcome == "verification_required"


def test_wrong_identity_is_refused_without_details(conn):
    r = check(conn, "arrependimento", "2025-10-28", email="intruso@jmail.com")
    assert r.outcome == "not_verified"
    assert r.days_elapsed is None and r.deadline is None


def test_non_returnable_item_blocks_regret(mutable_conn):
    mutable_conn.execute("UPDATE products SET name = 'Boquilha Yamaha 4C' WHERE product_id = 93")
    mutable_conn.commit()
    r = check(mutable_conn, "arrependimento", "2025-10-28")
    assert r.outcome == "not_eligible" and r.rule == "4.4"


def test_delivered_without_date_needs_human(mutable_conn):
    mutable_conn.execute("UPDATE orders SET estimated_delivery = NULL WHERE order_id = 1")
    mutable_conn.commit()
    assert check(mutable_conn, "arrependimento", "2025-10-28").outcome == "needs_human"


def test_now_override_env_is_used(conn, monkeypatch):
    monkeypatch.setenv("NOW_OVERRIDE", "2025-10-28T10:00:00")
    r = check_return_eligibility(conn, 1, "arrependimento", email=EMAIL)
    assert r.eligible is True and r.days_elapsed == 3
