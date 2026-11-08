from app.services import promotions


def test_apply_discount_rounds_half_up():
    assert promotions.apply_discount(5999, 8) == 5519.08
    assert promotions.apply_discount(100, 12.5) == 87.5


def test_expired_promotion_is_reported_without_discount(conn):
    status = promotions.get_promotion_status(conn, 93)  # só promoções inativas
    assert status.active is None
    assert len(status.expired) == 2
    assert "encerradas" in status.message
    assert "Não prometa" in status.message


def test_product_without_any_promotion(conn):
    status = promotions.get_promotion_status(conn, 81)
    assert status.active is None and status.expired == []
    assert "não tem promoção" in status.message


def test_unknown_product_returns_none(conn):
    assert promotions.get_promotion_status(conn, 99999) is None


def test_highest_active_discount_wins_when_several(mutable_conn):
    c = mutable_conn
    c.execute("INSERT INTO promotions VALUES (100, 95, 10, 'Teste A', 1)")
    c.execute("INSERT INTO promotions VALUES (101, 95, 20, 'Teste B', 1)")
    c.commit()
    status = promotions.get_promotion_status(c, 95)
    assert status.active.discount_percent == 20
    assert status.active.final_price_brl == 1759.2  # 2199 * 0.8


def test_summary_always_includes_original_price(conn):
    status = promotions.get_promotion_status(conn, 90)  # Crafter, 18% ativo
    assert "2.399,00" in status.active.summary
    assert "18% de desconto" in status.active.summary
