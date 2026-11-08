import pytest

from app.services import products


def test_price_query_by_exact_model(conn):
    result = products.search_products(conn, query="Takamine GD20")
    assert result.products[0].name.startswith("Takamine GD20")
    assert result.products[0].price_brl == 2199.0
    assert len(result.products) == 1


@pytest.mark.parametrize("query", ["gd20", "gd 20", "takamini gd20", "TAKAMINE gd-20"])
def test_search_is_tolerant_to_format_and_typos(conn, query):
    result = products.search_products(conn, query=query)
    assert result.products
    assert result.products[0].name.startswith("Takamine GD20")


def test_catalog_listing_by_category_and_price(conn):
    result = products.search_products(conn, category="violões", max_price=1000)
    assert result.total_matches > 0
    assert all(p.final_price_brl <= 1000 for p in result.products)
    assert all(p.category == "Violões" for p in result.products)
    assert all(p.availability == "available" for p in result.products)


def test_category_accepts_singular_without_accent(conn):
    assert products.resolve_categories(conn, "violao") == products.resolve_categories(conn, "Violões")


def test_unknown_category_returns_note_with_valid_names(conn):
    result = products.search_products(conn, category="amplificadores")
    assert result.products == []
    assert "não existe" in result.notes[0]
    assert "Guitarras" in result.notes[0]


def test_empty_category_is_flagged(conn):
    result = products.search_products(conn, category="sopro")
    assert result.products == []
    assert "não há produtos" in result.notes[0]


def test_active_product_without_stock_is_out_of_stock_with_alternatives(conn):
    result = products.search_products(conn, query="Giannini GF-3D Dreadnought")
    top = result.products[0]
    assert top.product_id == 96
    assert top.availability == "out_of_stock"
    assert result.alternatives
    assert all(a.availability == "available" for a in result.alternatives)
    assert all(a.product_id != 96 for a in result.alternatives)


def test_coming_soon_product_is_reported_not_sold(conn):
    result = products.search_products(conn, query="Kala KA-ABP-CTG")
    assert result.products[0].product_id == 130
    assert result.products[0].availability == "coming_soon"


def test_discontinued_product_found_by_name_but_hidden_in_listings(conn):
    by_name = products.search_products(conn, query="Shelby SN-7C")
    assert by_name.products[0].availability == "discontinued"
    listing = products.search_products(conn, category="violões")
    assert all(p.product_id != 113 for p in listing.products)


def test_active_promotion_shows_original_and_final_price(conn):
    info = products.get_product(conn, 94)  # Taylor 110e, 8% ativo
    assert info.price_brl == 5999.0
    assert info.promotion.discount_percent == 8
    assert info.final_price_brl == 5519.08
    assert info.pix_price_brl is None  # PIX não é cumulativo com promoção
    assert "5.999,00" in info.price_summary and "5.519,08" in info.price_summary


def test_regular_price_has_pix_discount(conn):
    info = products.get_product(conn, 95)  # GD20 sem promoção ativa
    assert info.promotion is None
    assert info.pix_price_brl == 2089.05


def test_price_filter_uses_effective_price(conn):
    # Taylor 110e custa 5999 de tabela, 5519,08 com a promoção
    result = products.search_products(conn, query="Taylor 110e", max_price=5600)
    assert [p.product_id for p in result.products] == [94]


def test_promotion_only_filter(conn):
    result = products.search_products(conn, on_promotion_only=True)
    assert {p.product_id for p in result.products} == {127, 121, 90, 94}


def test_categories_overview_shows_empty_ones(conn):
    cats = {c.name: c for c in products.list_categories(conn)}
    assert cats["Cordas Orquestrais"].total_products == 0
    assert cats["Violões"].available_products > 0
