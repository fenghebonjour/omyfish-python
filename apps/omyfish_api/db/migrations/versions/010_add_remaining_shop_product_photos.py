"""Swap the last two placeholder products (Braided Fishing Line, Insulated
Mug) to real CC0 photos, now that a suitable free match was found for both.
Re-seed image_url/image_credit only, scoped by id, so real
stock_quantity/active changes from live orders aren't reset.

Revision ID: 010
Revises: 009
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

from apps.omyfish_api.db.shop_seed import SHOP_SEED_PRODUCTS

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    shop_products = sa.table(
        "shop_products",
        sa.column("id", sa.Text), sa.column("image_url", sa.Text),
        sa.column("image_credit", sa.Text),
    )
    bind = op.get_bind()
    for product in SHOP_SEED_PRODUCTS:
        bind.execute(
            shop_products.update()
            .where(shop_products.c.id == product["id"])
            .values(image_url=product["image_url"], image_credit=product["image_credit"])
        )


def downgrade() -> None:
    pass
