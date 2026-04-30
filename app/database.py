import asyncpg
import logging
import re
import ssl
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

pool: Optional[asyncpg.Pool] = None


def _build_dsn() -> str:
    """Strip sslmode from DSN — asyncpg needs ssl passed as an explicit kwarg.
    Passing both causes a conflict that breaks Supabase's SNI-based tenant routing."""
    dsn = settings.DATABASE_URL
    dsn = re.sub(r"[?&]sslmode=[^&]*", "", dsn)
    dsn = re.sub(r"\?$", "", dsn)
    return dsn


def _build_ssl_ctx() -> ssl.SSLContext:
    """Create SSL context for Supabase. Verification is skipped because
    PgBouncer pooler endpoints use shared certs; encryption is still enforced."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def init_db():
    global pool
    try:
        pool = await asyncpg.create_pool(
            dsn=_build_dsn(),
            min_size=2,
            max_size=10,
            statement_cache_size=0,  # Required for Supabase PgBouncer
            ssl=_build_ssl_ctx(),
        )
        logger.info("Database pool initialised")
    except Exception as exc:
        logger.error(
            "Database connection failed: %s\n"
            "  → Use the Transaction pooler URL (port 6543) from:\n"
            "    Supabase Dashboard → Settings → Database → Connection string → URI\n"
            "  → Format: postgresql://postgres.[PROJECT-REF]:PASSWORD"
            "@aws-0-REGION.pooler.supabase.com:6543/postgres",
            exc,
        )
        raise


async def close_db():
    global pool
    if pool:
        await pool.close()
        logger.info("Database pool closed")


def get_pool() -> asyncpg.Pool:
    return pool


# ── Restaurant queries ────────────────────────────────────────────────────────

async def get_restaurant_by_phone_number_id(phone_number_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM restaurants WHERE phone_number_id = $1 AND active = true",
            phone_number_id,
        )
        return dict(row) if row else None


async def get_restaurant_by_id(restaurant_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM restaurants WHERE id = $1",
            restaurant_id,
        )
        return dict(row) if row else None


# ── Menu queries ──────────────────────────────────────────────────────────────

async def get_menu_items(restaurant_id: str, available_only: bool = True) -> list[dict]:
    async with pool.acquire() as conn:
        query = "SELECT * FROM menu_items WHERE restaurant_id = $1"
        if available_only:
            query += " AND available = true"
        query += " ORDER BY sort_order, name"
        rows = await conn.fetch(query, restaurant_id)
        return [dict(r) for r in rows]


async def get_menu_item(item_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM menu_items WHERE id = $1", item_id)
        return dict(row) if row else None


async def create_menu_item(restaurant_id: str, name: str, price: float,
                           category: str, description: str, sort_order: int = 0) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO menu_items (restaurant_id, name, price, category, description, sort_order)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            restaurant_id, name, price, category, description, sort_order,
        )
        return dict(row)


async def toggle_menu_item(item_id: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE menu_items SET available = NOT available WHERE id = $1 RETURNING *",
            item_id,
        )
        return dict(row) if row else None


# ── Order queries ─────────────────────────────────────────────────────────────

async def create_order(restaurant_id: str, customer_phone: str, items: list,
                       total: float, order_type: str, delivery_address: str = "",
                       notes: str = "") -> dict:
    import json
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO orders (restaurant_id, customer_phone, items, total, order_type, delivery_address, notes)
               VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7) RETURNING *""",
            restaurant_id, customer_phone, json.dumps(items), total, order_type, delivery_address, notes,
        )
        return dict(row)


async def get_order(order_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        return dict(row) if row else None


async def update_order_status(order_id: str, status: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE orders SET status = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
            status, order_id,
        )
        return dict(row) if row else None


async def get_orders_for_restaurant(restaurant_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE restaurant_id = $1 ORDER BY created_at DESC",
            restaurant_id,
        )
        return [dict(r) for r in rows]


async def get_todays_orders(restaurant_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM orders
               WHERE restaurant_id = $1
                 AND created_at >= CURRENT_DATE
               ORDER BY created_at DESC""",
            restaurant_id,
        )
        return [dict(r) for r in rows]


# ── Customer queries ──────────────────────────────────────────────────────────

async def upsert_customer(restaurant_id: str, phone: str,
                          name: str = "", spent: float = 0.0) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO customers (restaurant_id, phone, name, order_count, total_spent, last_order_at)
               VALUES ($1, $2, $3, 1, $4, NOW())
               ON CONFLICT (restaurant_id, phone)
               DO UPDATE SET
                   order_count = customers.order_count + 1,
                   total_spent = customers.total_spent + EXCLUDED.total_spent,
                   last_order_at = NOW()
               RETURNING *""",
            restaurant_id, phone, name, spent,
        )
        return dict(row)


async def get_opted_in_customers(restaurant_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM customers WHERE restaurant_id = $1 AND opted_in = true",
            restaurant_id,
        )
        return [dict(r) for r in rows]


async def get_customer_count(restaurant_id: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM customers WHERE restaurant_id = $1",
            restaurant_id,
        )
