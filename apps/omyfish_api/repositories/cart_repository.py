from sqlalchemy import text

from apps.omyfish_api.db.engine import get_db, new_id


class CartRepository:

    def get_or_create(self, user_id: str | None = None, guest_token: str | None = None) -> dict:
        """Exactly one of user_id/guest_token must be set — same XOR invariant
        enforced at the DB level by the shop_carts CHECK constraint."""
        assert (user_id is None) != (guest_token is None)
        existing = self._find(user_id=user_id, guest_token=guest_token)
        if existing:
            return existing
        cart_id = new_id()
        with get_db() as db:
            db.execute(
                text(
                    "INSERT INTO shop_carts (id, user_id, guest_token) "
                    "VALUES (:id, :uid, :gt)"
                ),
                {"id": cart_id, "uid": user_id, "gt": guest_token},
            )
        return self._find(user_id=user_id, guest_token=guest_token)

    def _find(self, user_id: str | None = None, guest_token: str | None = None) -> dict | None:
        column = "user_id" if user_id is not None else "guest_token"
        value = user_id if user_id is not None else guest_token
        with get_db() as db:
            row = db.execute(
                text(f"SELECT * FROM shop_carts WHERE {column} = :value"),
                {"value": value},
            ).fetchone()
        return dict(row._mapping) if row else None

    def get_items(self, cart_id: str) -> list[dict]:
        with get_db() as db:
            rows = db.execute(
                text("SELECT product_id, quantity FROM shop_cart_items WHERE cart_id = :cid"),
                {"cid": cart_id},
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def add_item(self, cart_id: str, product_id: str, qty: int) -> None:
        items = {i["product_id"]: i["quantity"] for i in self.get_items(cart_id)}
        new_qty = items.get(product_id, 0) + qty
        self.set_quantity(cart_id, product_id, new_qty)

    def set_quantity(self, cart_id: str, product_id: str, qty: int) -> None:
        with get_db() as db:
            if qty <= 0:
                db.execute(
                    text(
                        "DELETE FROM shop_cart_items WHERE cart_id = :cid AND product_id = :pid"
                    ),
                    {"cid": cart_id, "pid": product_id},
                )
                return
            db.execute(
                text(
                    "DELETE FROM shop_cart_items WHERE cart_id = :cid AND product_id = :pid"
                ),
                {"cid": cart_id, "pid": product_id},
            )
            db.execute(
                text(
                    "INSERT INTO shop_cart_items (cart_id, product_id, quantity) "
                    "VALUES (:cid, :pid, :qty)"
                ),
                {"cid": cart_id, "pid": product_id, "qty": qty},
            )

    def clear(self, cart_id: str) -> None:
        with get_db() as db:
            db.execute(
                text("DELETE FROM shop_cart_items WHERE cart_id = :cid"), {"cid": cart_id}
            )

    def delete_by_guest_token(self, guest_token: str) -> None:
        with get_db() as db:
            db.execute(
                text("DELETE FROM shop_carts WHERE guest_token = :gt"), {"gt": guest_token}
            )

    def merge_guest_into_user(self, user_id: str, guest_token: str) -> dict:
        """Folds a guest cart's items into the user's account cart (summing
        quantities for overlapping products), then deletes the now-redundant
        guest cart row. A no-op if no guest cart exists for that token."""
        guest_cart = self._find(guest_token=guest_token)
        user_cart = self.get_or_create(user_id=user_id)
        if not guest_cart:
            return user_cart
        for item in self.get_items(guest_cart["id"]):
            self.add_item(user_cart["id"], item["product_id"], item["quantity"])
        self.delete_by_guest_token(guest_token)
        return self._find(user_id=user_id)
