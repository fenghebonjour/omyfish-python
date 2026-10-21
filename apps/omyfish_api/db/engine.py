import logging
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGIS = DATABASE_URL.startswith("postgresql")

if not IS_POSTGIS:
    _db_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "observations.db"
    DATABASE_URL = f"sqlite:///{_db_path}"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_connect_args = {} if IS_POSTGIS else {"check_same_thread": False}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
Session = sessionmaker(bind=engine)

_db_initialized = False


def init_db():
    """Create tables via raw DDL. Used for SQLite; PostGIS uses Alembic migrations."""
    with engine.connect() as conn:
        if IS_POSTGIS:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS observations (
                    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    species_name     TEXT,
                    scientific_name  TEXT,
                    confidence       FLOAT,
                    timestamp        TIMESTAMPTZ DEFAULT now(),
                    latitude         FLOAT,
                    longitude        FLOAT,
                    geom             GEOGRAPHY(POINT, 4326),
                    image_url        TEXT,
                    user_id          TEXT,
                    source           TEXT DEFAULT 'upload'
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS observations_geom_idx "
                "ON observations USING GIST(geom)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS observations_user_ts_idx "
                "ON observations (user_id, timestamp DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS observations_ts_idx "
                "ON observations (timestamp DESC)"
            ))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS observations (
                    id               TEXT PRIMARY KEY,
                    species_name     TEXT,
                    scientific_name  TEXT,
                    confidence       REAL,
                    timestamp        TEXT DEFAULT (datetime('now')),
                    latitude         REAL,
                    longitude        REAL,
                    image_url        TEXT,
                    user_id          TEXT,
                    source           TEXT DEFAULT 'upload'
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS observations_user_ts_idx "
                "ON observations (user_id, timestamp DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS observations_ts_idx "
                "ON observations (timestamp DESC)"
            ))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id               TEXT PRIMARY KEY,
                    email            TEXT UNIQUE NOT NULL,
                    hashed_password  TEXT NOT NULL,
                    role             TEXT NOT NULL DEFAULT 'user',
                    is_active        INTEGER NOT NULL DEFAULT 1,
                    created_at       TEXT DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id                      TEXT PRIMARY KEY,
                    user_id                 TEXT NOT NULL UNIQUE,
                    status                  TEXT NOT NULL DEFAULT 'trialing',
                    plan                    TEXT,
                    trial_end               TEXT,
                    current_period_end      TEXT,
                    stripe_customer_id      TEXT,
                    stripe_subscription_id  TEXT,
                    created_at              TEXT DEFAULT (datetime('now')),
                    updated_at              TEXT DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key  TEXT NOT NULL,
                    endpoint         TEXT NOT NULL,
                    user_id          TEXT NOT NULL,
                    status           TEXT NOT NULL DEFAULT 'pending',
                    result_json      TEXT,
                    created_at       TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (idempotency_key, endpoint)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS processed_webhook_events (
                    event_id      TEXT PRIMARY KEY,
                    processed_at  TEXT DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shop_products (
                    id              TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    description     TEXT,
                    price_cents     INTEGER NOT NULL,
                    image_url       TEXT,
                    stock_quantity  INTEGER NOT NULL DEFAULT 0,
                    active          INTEGER NOT NULL DEFAULT 1
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shop_carts (
                    id           TEXT PRIMARY KEY,
                    user_id      TEXT UNIQUE,
                    guest_token  TEXT UNIQUE,
                    CHECK ((user_id IS NULL) != (guest_token IS NULL))
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shop_cart_items (
                    cart_id     TEXT NOT NULL REFERENCES shop_carts(id) ON DELETE CASCADE,
                    product_id  TEXT NOT NULL,
                    quantity    INTEGER NOT NULL,
                    PRIMARY KEY (cart_id, product_id)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shop_orders (
                    id                        TEXT PRIMARY KEY,
                    user_id                   TEXT,
                    guest_email               TEXT,
                    total_cents               INTEGER NOT NULL,
                    status                    TEXT NOT NULL DEFAULT 'pending_payment',
                    stripe_session_id         TEXT,
                    stripe_payment_intent_id  TEXT,
                    created_at                TEXT DEFAULT (datetime('now')),
                    paid_at                   TEXT,
                    return_requested_at       TEXT,
                    returned_at               TEXT,
                    return_reason             TEXT,
                    shipping_recipient_name   TEXT,
                    shipping_line1            TEXT,
                    shipping_line2            TEXT,
                    shipping_city             TEXT,
                    shipping_state            TEXT,
                    shipping_postal_code      TEXT,
                    shipping_country          TEXT,
                    CHECK ((user_id IS NULL) != (guest_email IS NULL))
                )
            """))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS shop_orders_stripe_session_id_idx "
                "ON shop_orders (stripe_session_id) WHERE stripe_session_id IS NOT NULL"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS shop_orders_user_id_idx ON shop_orders (user_id)"
            ))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shop_order_lines (
                    order_id          TEXT NOT NULL REFERENCES shop_orders(id) ON DELETE CASCADE,
                    line_index        INTEGER NOT NULL,
                    product_id        TEXT NOT NULL,
                    product_name      TEXT NOT NULL,
                    unit_price_cents  INTEGER NOT NULL,
                    quantity          INTEGER NOT NULL,
                    PRIMARY KEY (order_id, line_index)
                )
            """))
            from apps.omyfish_api.db.shop_seed import SHOP_SEED_PRODUCTS
            for product in SHOP_SEED_PRODUCTS:
                conn.execute(text(
                    "INSERT OR IGNORE INTO shop_products "
                    "(id, name, description, price_cents, image_url, stock_quantity, active) "
                    "VALUES (:id, :name, :description, :price_cents, :image_url, :stock_quantity, :active)"
                ), product)
        conn.commit()


def run_migrations():
    """Run Alembic migrations. PostGIS only."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


def ensure_db() -> bool:
    """Idempotent DB setup: Alembic for PostGIS, DDL shim for SQLite."""
    global _db_initialized
    if not _db_initialized:
        try:
            if IS_POSTGIS:
                run_migrations()
            else:
                init_db()
            _db_initialized = True
        except Exception:
            # A bad migration/DDL failure used to be swallowed here with no trace at all —
            # every caller (both the FastAPI routes and Streamlit's own in-process calls)
            # just silently kept retrying the full setup on every request against a DB that
            # may never come up. Logged loudly now so a real failure is discoverable instead
            # of only visible as db_ready() staying False forever with no explanation
            # (BACKLOG.md item B, WEAKNESS_AUDIT.md §3.1). Still not re-raised — this function
            # is called from many places, including Streamlit script runs that don't expect
            # it to raise — so callers keep getting a clean False instead of a crash.
            logger.exception("Database setup failed — db_ready() will keep returning False")
    return _db_initialized


def db_ready() -> bool:
    return _db_initialized


def new_id() -> str:
    """Generate a UUID string (works for both backends)."""
    return str(uuid.uuid4())


@contextmanager
def get_db():
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
