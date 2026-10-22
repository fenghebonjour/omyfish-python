"""Fix shop_products.image_url: migration 006 seeded raw (non-base64) SVG
data URIs whose hex colors' "#" gets parsed as the URL fragment delimiter,
truncating the SVG and breaking rendering. Re-seed image_url only, scoped
by id, so real stock_quantity/active changes from live orders aren't reset.

Revision ID: 007
Revises: 006
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

from apps.omyfish_api.db.shop_seed import SHOP_SEED_PRODUCTS

revision = "007"
down_revision = "006"
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
