"""Initial schema — observations table with PostGIS geometry

Revision ID: 001
Revises:
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))

    op.create_table(
        "observations",
        sa.Column(
            "id",
            sa.String,
            server_default=sa.text("gen_random_uuid()::text"),
            primary_key=True,
        ),
        sa.Column("species_name", sa.Text),
        sa.Column("scientific_name", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("image_url", sa.Text),
        sa.Column("user_id", sa.Text),
        sa.Column("source", sa.Text, server_default="upload"),
    )

    # PostGIS geometry column and spatial index (raw DDL — no geoalchemy2 required)
    conn.execute(sa.text(
        "ALTER TABLE observations ADD COLUMN IF NOT EXISTS "
        "geom GEOGRAPHY(POINT, 4326)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS observations_geom_idx "
        "ON observations USING GIST(geom)"
    ))


def downgrade() -> None:
    op.drop_table("observations")
