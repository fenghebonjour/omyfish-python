import sys
from pathlib import Path

# Ensure repo root is importable when alembic runs from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from alembic import context
from apps.omyfish_api.db.engine import engine


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline migration mode is not supported.")
else:
    run_migrations_online()
