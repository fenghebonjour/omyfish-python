"""Add idempotency_keys table

Revision ID: 004
Revises: 003
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="pending", nullable=False),
        sa.Column("result_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("idempotency_key", "endpoint"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
