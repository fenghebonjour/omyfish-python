"""Add processed_webhook_events table

Revision ID: 005
Revises: 004
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_webhook_events",
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("processed_webhook_events")
