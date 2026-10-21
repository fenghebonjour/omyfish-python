from sqlalchemy import text

from apps.omyfish_api.db.engine import get_db


class ProductRepository:

    def list_active(self) -> list[dict]:
        with get_db() as db:
            rows = db.execute(
                text("SELECT * FROM shop_products WHERE active = :active ORDER BY name"),
                {"active": True},
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get(self, product_id: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text("SELECT * FROM shop_products WHERE id = :id"),
                {"id": product_id},
            ).fetchone()
        return dict(row._mapping) if row else None

    def decrease_stock(self, product_id: str, qty: int) -> None:
        with get_db() as db:
            db.execute(
                text(
                    "UPDATE shop_products SET stock_quantity = stock_quantity - :qty "
                    "WHERE id = :id"
                ),
                {"qty": qty, "id": product_id},
            )

    def restock(self, product_id: str, qty: int) -> None:
        with get_db() as db:
            db.execute(
                text(
                    "UPDATE shop_products SET stock_quantity = stock_quantity + :qty "
                    "WHERE id = :id"
                ),
                {"qty": qty, "id": product_id},
            )
