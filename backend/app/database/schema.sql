-- Schema do banco SQLite. Recriado do zero a cada execução do seed.

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    name_norm   TEXT NOT NULL,
    description TEXT
);

CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    name_norm      TEXT NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(category_id),
    description    TEXT,
    price_brl      REAL NOT NULL CHECK (price_brl > 0),
    stock_quantity INTEGER NOT NULL,
    status         TEXT NOT NULL,
    specs_json     TEXT NOT NULL DEFAULT '{}',
    search_text    TEXT NOT NULL,
    created_at     TEXT
);
CREATE INDEX idx_products_category ON products(category_id);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT,
    phone_digits TEXT,
    email        TEXT,
    email_norm   TEXT,
    city         TEXT,
    city_norm    TEXT
);

CREATE TABLE promotions (
    promotion_id     INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent REAL NOT NULL CHECK (discount_percent > 0 AND discount_percent < 100),
    description      TEXT,
    is_active        INTEGER NOT NULL CHECK (is_active IN (0, 1))
);
CREATE INDEX idx_promotions_product ON promotions(product_id);

CREATE TABLE orders (
    order_id           INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date         TEXT NOT NULL,
    status             TEXT NOT NULL,
    total_brl          REAL NOT NULL,
    payment_method     TEXT NOT NULL,
    payment_type       TEXT NOT NULL,
    installments       INTEGER NOT NULL DEFAULT 1,
    tracking_code      TEXT,
    estimated_delivery TEXT,
    notes              TEXT
);
CREATE INDEX idx_orders_customer ON orders(customer_id);

CREATE TABLE order_items (
    item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0)
);
CREATE INDEX idx_order_items_order ON order_items(order_id);

-- Inconsistências encontradas nos dados de origem (ver docs/data_quality.md)
CREATE TABLE data_quality_issues (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code      TEXT NOT NULL,
    severity  TEXT NOT NULL,
    entity    TEXT NOT NULL,
    entity_id TEXT,
    message   TEXT NOT NULL
);
