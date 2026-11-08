import pytest

from app.services.shipping import calculate_shipping, is_large_item


@pytest.mark.parametrize(
    "total, cost",
    [(499.99, 35.0), (500.0, 35.0), (500.01, 0.0), (159.9, 35.0), (8000, 0.0)],
)
def test_metro_area_free_shipping_only_above_500(total, cost):
    quote = calculate_shipping("Campo Grande", total)
    assert quote.region == "metropolitana"
    assert quote.options[0].cost_brl == cost
    assert quote.options[0].deadline == "1 a 3 dias úteis"


def test_city_matching_ignores_case_and_accents():
    assert calculate_shipping("campo  grande", 100).region == "metropolitana"


def test_other_cities_use_carriers_without_inventing_a_price():
    quote = calculate_shipping("Dourados", 1000)
    assert quote.region == "outras_cidades"
    assert {o.carrier for o in quote.options} == {"PAC (Correios)", "SEDEX (Correios)", "Jadlog (.package)"}
    assert all(o.cost_brl is None for o in quote.options)
    assert next(o for o in quote.options if "SEDEX" in o.carrier).deadline == "2 a 5 dias úteis"


def test_unknown_city_asks_for_it():
    quote = calculate_shipping(None, 1000)
    assert quote.region == "desconhecida" and quote.options == []
    assert any("cidade" in n for n in quote.notes)


def test_large_items_need_special_quote():
    assert is_large_item("Bateria Acústica Yamaha Kit 1 Studio")
    assert not is_large_item("Yamaha C40 Nylon Natural")
    quote = calculate_shipping("Corumbá", 13285, has_large_items=True)
    assert quote.requires_special_quote is True
