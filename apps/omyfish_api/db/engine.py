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
