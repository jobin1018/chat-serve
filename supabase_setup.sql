-- ============================================================
-- WhatsApp Restaurant Ordering Bot — Supabase Schema
-- Run this once in the Supabase SQL editor (Dashboard → SQL)
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── restaurants ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS restaurants (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    whatsapp_num     TEXT NOT NULL,          -- display number e.g. +971501234567
    phone_number_id  TEXT NOT NULL UNIQUE,   -- Meta phone_number_id
    kitchen_num      TEXT NOT NULL,          -- WhatsApp number for kitchen alerts
    owner_num        TEXT NOT NULL,
    active           BOOLEAN NOT NULL DEFAULT true,
    opening_hours    TEXT NOT NULL DEFAULT '9:00 AM – 11:00 PM',
    delivery_areas   TEXT NOT NULL DEFAULT 'Al Nahda, Sharjah',
    min_order        DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── menu_items ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS menu_items (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    price          DECIMAL(10,2) NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    category       TEXT NOT NULL,
    available      BOOLEAN NOT NULL DEFAULT true,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant ON menu_items(restaurant_id);

-- ── orders ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id   UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    customer_phone  TEXT NOT NULL,
    items           JSONB NOT NULL DEFAULT '[]',
    total           DECIMAL(10,2) NOT NULL DEFAULT 0,
    order_type        TEXT NOT NULL DEFAULT 'pickup' CHECK (order_type IN ('pickup', 'delivery')),
    delivery_address  TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new','confirmed','preparing','ready','completed','cancelled')),
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_restaurant ON orders(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- ── customers ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    phone          TEXT NOT NULL,
    name           TEXT NOT NULL DEFAULT '',
    order_count    INTEGER NOT NULL DEFAULT 0,
    total_spent    DECIMAL(10,2) NOT NULL DEFAULT 0,
    opted_in       BOOLEAN NOT NULL DEFAULT true,
    last_order_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (restaurant_id, phone)
);

CREATE INDEX IF NOT EXISTS idx_customers_restaurant ON customers(restaurant_id);

-- ============================================================
-- SEED DATA — Al Nahda Demo Kitchen
-- UPDATE phone_number_id and whatsapp_num after Meta setup
-- ============================================================

INSERT INTO restaurants (
  name, whatsapp_num, phone_number_id,
  kitchen_num, owner_num, active,
  opening_hours, delivery_areas, min_order
) VALUES (
  'Al Nahda Demo Kitchen',
  '+15556316066',
  '1072617075937276',
  '+971555443741',
  '+971555443741',
  true,
  '10:00 AM - 11:00 PM daily',
  'Al Nahda, Al Qusais, Mirdif',
  30
);

-- Store the restaurant ID for seeding menu items
DO $$
DECLARE
    rest_id UUID;
BEGIN
    SELECT id INTO rest_id FROM restaurants WHERE name = 'Al Nahda Demo Kitchen' LIMIT 1;

    -- ── MAINS ────────────────────────────────────────────────────────────────
    INSERT INTO menu_items (restaurant_id, name, price, description, category, sort_order) VALUES
    (rest_id, 'Chicken Biryani',       25.00, 'Fragrant basmati rice slow-cooked with tender chicken and aromatic spices',     'Mains', 1),
    (rest_id, 'Mutton Biryani',        35.00, 'Rich dum biryani with succulent mutton and saffron-infused rice',                'Mains', 2),
    (rest_id, 'Chicken Karahi',        45.00, 'Wok-tossed chicken in fresh tomatoes, ginger, green chilli & desi ghee',        'Mains', 3),
    (rest_id, 'Dal Makhani',           20.00, 'Slow-cooked black lentils in creamy butter and tomato gravy — veg',             'Mains', 4),
    (rest_id, 'Chicken Tikka Masala',  40.00, 'Grilled tikka pieces in velvety tomato and cream masala sauce',                 'Mains', 5),
    (rest_id, 'Palak Paneer',          22.00, 'Cottage cheese cubes in spiced spinach gravy — vegetarian',                    'Mains', 6),

    -- ── STARTERS ─────────────────────────────────────────────────────────────
    (rest_id, 'Chicken Seekh Kebab',   30.00, 'Minced chicken skewers with herbs, charcoal-grilled (4 pcs)',                  'Starters', 1),
    (rest_id, 'Vegetable Samosa',       8.00, 'Crispy pastry stuffed with spiced potato and peas (2 pcs)',                    'Starters', 2),
    (rest_id, 'Onion Pakora',          12.00, 'Golden fried onion fritters with mint chutney',                                'Starters', 3),

    -- ── BREADS ───────────────────────────────────────────────────────────────
    (rest_id, 'Plain Naan',             3.00, 'Soft leavened bread baked in tandoor',                                         'Breads', 1),
    (rest_id, 'Garlic Naan',            5.00, 'Tandoor naan brushed with garlic butter and coriander',                        'Breads', 2),
    (rest_id, 'Butter Paratha',         4.00, 'Flaky layered flatbread with butter — 2 pcs',                                  'Breads', 3),

    -- ── BEVERAGES ────────────────────────────────────────────────────────────
    (rest_id, 'Mango Lassi',           12.00, 'Thick chilled yoghurt drink with Alphonso mango',                              'Beverages', 1),
    (rest_id, 'Mint Lemonade',         10.00, 'Fresh lemon, mint, and a hint of black salt — refreshing',                     'Beverages', 2);

END $$;
