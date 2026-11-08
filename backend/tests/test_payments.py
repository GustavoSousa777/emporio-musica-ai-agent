import pytest

from app.services.payments import get_payment_options, pix_price, validate_installment


def test_pix_has_five_percent_off():
    assert pix_price(2199) == 2089.05
    assert get_payment_options(3000).pix_total_brl == 2850.0


def test_promotional_price_has_no_pix_discount():
    options = get_payment_options(5519.08, promotional=True)
    assert options.pix_total_brl is None
    assert options.pix_discount_applied is False
    assert any("não se aplica" in n for n in options.notes)


@pytest.mark.parametrize(
    "amount, expected_max",
    [
        (3000, 12),  # 250 por parcela em 12x
        (1000, 10),  # 10x = 100; 11x = 90,91 < 100
        (599, 6),    # 6x = 99,83 >= 80; 7x = 85,57 < 100
        (100, 2),    # 2x = 50; 3x = 33,33 < 50
        (40, 1),     # nenhuma parcela >= 50
    ],
)
def test_max_installments_follow_minimum_parcel(amount, expected_max):
    assert get_payment_options(amount).max_installments == expected_max


def test_installment_tiers_boundaries():
    assert validate_installment(300, 6)[0] is False   # 50 < 80
    assert validate_installment(480, 6)[0] is True    # 80 = mínimo
    assert validate_installment(700, 7)[0] is True    # 100 = mínimo
    assert validate_installment(699, 7)[0] is False
    assert validate_installment(150, 3)[0] is True    # 50 = mínimo
    assert validate_installment(1000, 13)[0] is False


def test_installment_value_is_rounded():
    ok, _, value = validate_installment(1000, 3)
    assert ok and value == 333.33


def test_combined_payment_only_above_2000():
    assert get_payment_options(2000).can_combine_payment_methods is False
    assert get_payment_options(2000.01).can_combine_payment_methods is True


def test_credit_options_are_interest_free():
    options = get_payment_options(1200)
    assert all(o.total_brl == 1200.0 for o in options.credit)
