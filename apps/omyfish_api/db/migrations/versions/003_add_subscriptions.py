"""Add subscriptions table

Revision ID: 003
Revises: 002
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String, server_default=sa.text("gen_random_uuid()::text"), primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, unique=True),
        sa.Column("status", sa.Text, server_default="trialing", nullable=False),
        sa.Column("plan", sa.Text, nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.Text, nullable=True),
        sa.Column("stripe_subscription_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("subscriptions_status_idx", "subscriptions", ["status"])


def downgrade() -> None:
    op.drop_index("subscriptions_status_idx")
    op.drop_table("subscriptions")
