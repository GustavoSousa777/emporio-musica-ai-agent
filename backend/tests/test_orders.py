import pytest

from app.services import orders
from app.services.orders import NOT_VERIFIED_MESSAGE


def test_lookup_with_email(conn, customers):
    email, _ = customers[1]
    result = orders.lookup_order(conn, 1, email=email)
    assert result.status == "ok"
    order = result.order
    assert order.customer_first_name == "Pedro"
    assert order.status == "delivered"
    assert order.tracking_code == "BRAB1234567BR"
    assert order.total_brl == 11499.0
    assert order.payment_method_label == "PIX"
    assert order.items[0].quantity == 1


@pytest.mark.parametrize(
    "phone", ["(67) 98432-1098", "67984321098", "98432-1098", "+55 67 98432 1098", "984321098"]
)
def test_phone_formats_are_accepted(conn, phone):
    assert orders.lookup_order(conn, 1, phone=phone).status == "ok"


def test_email_is_case_insensitive(conn):
    assert orders.lookup_order(conn, 1, email=" Pedro.Oliveira@JMAIL.com ").status == "ok"


def test_no_verification_data_is_refused(conn):
    result = orders.lookup_order(conn, 1)
    assert result.status == "verification_required"
    assert result.order is None


def test_wrong_email_and_unknown_order_look_identical(conn):
    wrong = orders.lookup_order(conn, 1, email="outra.pessoa@jmail.com")
    missing = orders.lookup_order(conn, 99999, email="pedro.oliveira@jmail.com")
    assert wrong.status == missing.status == "not_verified"
    assert wrong.message == missing.message == NOT_VERIFIED_MESSAGE
    assert wrong.order is None and missing.order is None


def test_other_customers_phone_does_not_unlock_order(conn):
    # telefone da Ana (pedido 8) não abre o pedido 1 (Pedro)
    assert orders.lookup_order(conn, 1, phone="(67) 99654-7821").status == "not_verified"


def test_all_provided_factors_must_match(conn):
    result = orders.lookup_order(conn, 1, email="pedro.oliveira@jmail.com", phone="(67) 99654-7821")
    assert result.status == "not_verified"


def test_very_short_phone_is_rejected(conn):
    assert orders.lookup_order(conn, 1, phone="1098").status == "not_verified"


def test_shipped_order_has_tracking_and_estimate(conn, customers):
    email, _ = customers[8]
    order = orders.lookup_order(conn, 8, email=email).order
    assert order.status_label == "Enviado"
    assert order.tracking_code == "BRJL5544332BR"
    assert order.estimated_delivery == "2026-02-28"


def test_pending_order_has_no_tracking(conn):
    # pedido 13: cliente 8
    row = conn.execute("SELECT email FROM customers WHERE customer_id = 8").fetchone()
    order = orders.lookup_order(conn, 13, email=row["email"]).order
    assert order.status == "pending"
    assert order.tracking_code is None and order.estimated_delivery is None


def test_cancelled_order_exposes_reason(conn):
    row = conn.execute("SELECT email FROM customers WHERE customer_id = 17").fetchone()
    order = orders.lookup_order(conn, 18, email=row["email"]).order
    assert order.status == "cancelled"
    assert "fora de estoque" in order.notes


def test_credit_installments_label(conn):
    row = conn.execute("SELECT email FROM customers WHERE customer_id = 7").fetchone()
    order = orders.lookup_order(conn, 2, email=row["email"]).order
    assert order.payment_method_label == "Cartão de crédito em 6x"
