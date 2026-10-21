"""Add shop_products/shop_carts/shop_cart_items/shop_orders/shop_order_lines
tables (Omyshop: catalog, cart, one-time checkout, orders, returns)

Revision ID: 006
Revises: 005
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.omyfish_api.db.shop_seed import SHOP_SEED_PRODUCTS

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_products",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price_cents", sa.BigInteger, nullable=False),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("stock_quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "shop_carts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, nullable=True, unique=True),
        sa.Column("guest_token", sa.Text, nullable=True, unique=True),
        sa.CheckConstraint(
            "(user_id IS NULL) != (guest_token IS NULL)", name="shop_carts_owner_check"
        ),
    )

    op.create_table(
        "shop_cart_items",
        sa.Column("cart_id", sa.Text,
                  sa.ForeignKey("shop_carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("cart_id", "product_id"),
    )

    op.create_table(
        "shop_orders",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, nullable=True),
        sa.Column("guest_email", sa.Text, nullable=True),
        sa.Column("total_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending_payment"),
        sa.Column("stripe_session_id", sa.Text, nullable=True),
        sa.Column("stripe_payment_intent_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_reason", sa.Text, nullable=True),
        sa.Column("shipping_recipient_name", sa.Text, nullable=True),
        sa.Column("shipping_line1", sa.Text, nullable=True),
        sa.Column("shipping_line2", sa.Text, nullable=True),
        sa.Column("shipping_city", sa.Text, nullable=True),
        sa.Column("shipping_state", sa.Text, nullable=True),
        sa.Column("shipping_postal_code", sa.Text, nullable=True),
        sa.Column("shipping_country", sa.Text, nullable=True),
        sa.CheckConstraint(
            "(user_id IS NULL) != (guest_email IS NULL)", name="shop_orders_owner_check"
        ),
    )
    op.create_index(
        "shop_orders_stripe_session_id_idx", "shop_orders", ["stripe_session_id"],
        unique=True, postgresql_where=sa.text("stripe_session_id IS NOT NULL"),
    )
    op.create_index("shop_orders_user_id_idx", "shop_orders", ["user_id"])

    op.create_table(
        "shop_order_lines",
        sa.Column("order_id", sa.Text,
                  sa.ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_index", sa.Integer, nullable=False),
        sa.Column("product_id", sa.Text, nullable=False),
        sa.Column("product_name", sa.Text, nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("order_id", "line_index"),
    )

    shop_products = sa.table(
        "shop_products",
        sa.column("id", sa.Text), sa.column("name", sa.Text),
        sa.column("description", sa.Text), sa.column("price_cents", sa.BigInteger),
        sa.column("image_url", sa.Text), sa.column("stock_quantity", sa.Integer),
        sa.column("active", sa.Boolean),
    )
    bind = op.get_bind()
    for product in SHOP_SEED_PRODUCTS:
        bind.execute(
            pg_insert(shop_products).values(**product).on_conflict_do_nothing(
                index_elements=["id"]
            )
        )


def downgrade() -> None:
    op.drop_table("shop_order_lines")
    op.drop_index("shop_orders_user_id_idx", table_name="shop_orders")
    op.drop_index("shop_orders_stripe_session_id_idx", table_name="shop_orders")
    op.drop_table("shop_orders")
    op.drop_table("shop_cart_items")
    op.drop_table("shop_carts")
    op.drop_table("shop_products")
