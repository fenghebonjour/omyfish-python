"""Add shop_products.image_credit (attribution for CC BY/BY-SA licensed
product photos; null for public-domain and placeholder images) and swap six
products from SVG placeholders to real licensed photos. Scoped to
image_url/image_credit only so real stock_quantity/active changes from live
orders aren't reset.

Revision ID: 009
Revises: 008
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

from apps.omyfish_api.db.shop_seed import SHOP_SEED_PRODUCTS

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shop_products", sa.Column("image_credit", sa.Text, nullable=True))

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
    op.drop_column("shop_products", "image_credit")
