"""Restyle shop_products placeholder images to match omyfish-java's V4 seed
style: 400x300 canvas, two centered text lines (product name + category)
instead of one. Re-seed image_url only, scoped by id, so real
stock_quantity/active changes from live orders aren't reset.

Revision ID: 008
Revises: 007
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

from apps.omyfish_api.db.shop_seed import SHOP_SEED_PRODUCTS

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    shop_products = sa.table(
        "shop_products", sa.column("id", sa.Text), sa.column("image_url", sa.Text)
    )
    bind = op.get_bind()
    for product in SHOP_SEED_PRODUCTS:
        bind.execute(
            shop_products.update()
            .where(shop_products.c.id == product["id"])
            .values(image_url=product["image_url"])
        )


def downgrade() -> None:
    pass
