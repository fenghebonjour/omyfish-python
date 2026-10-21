from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from apps.omyfish_api.db.engine import get_db, new_id

RETURN_WINDOW_DAYS = 30


class InvalidOrderState(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class OrderRepository:

    def create_pending(self, user_id: str | None, guest_email: str | None,
                        lines: list[dict], total_cents: int) -> str:
        """lines: [{"product_id", "product_name", "unit_price_cents", "quantity"}, ...]"""
        assert (user_id is None) != (guest_email is None)
        order_id = new_id()
        with get_db() as db:
            db.execute(
                text(
                    "INSERT INTO shop_orders (id, user_id, guest_email, total_cents, status) "
                    "VALUES (:id, :uid, :email, :total, 'pending_payment')"
                ),
                {"id": order_id, "uid": user_id, "email": guest_email, "total": total_cents},
            )
            for i, line in enumerate(lines):
                db.execute(
                    text(
                        "INSERT INTO shop_order_lines "
                        "(order_id, line_index, product_id, product_name, unit_price_cents, quantity) "
                        "VALUES (:oid, :idx, :pid, :pname, :price, :qty)"
                    ),
                    {
                        "oid": order_id, "idx": i, "pid": line["product_id"],
                        "pname": line["product_name"], "price": line["unit_price_cents"],
                        "qty": line["quantity"],
                    },
                )
        return order_id

    def get(self, order_id: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text("SELECT * FROM shop_orders WHERE id = :id"), {"id": order_id}
            ).fetchone()
            if not row:
                return None
            lines = db.execute(
                text(
                    "SELECT * FROM shop_order_lines WHERE order_id = :id ORDER BY line_index"
                ),
                {"id": order_id},
            ).fetchall()
        order = self._effective(dict(row._mapping))
        order["lines"] = [dict(l._mapping) for l in lines]
        return order

    def get_by_stripe_session(self, session_id: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text("SELECT id FROM shop_orders WHERE stripe_session_id = :sid"),
                {"sid": session_id},
            ).fetchone()
        return self.get(row[0]) if row else None

    def list_for_user(self, user_id: str) -> list[dict]:
        with get_db() as db:
            rows = db.execute(
                text(
                    "SELECT id FROM shop_orders WHERE user_id = :uid ORDER BY created_at DESC"
                ),
                {"uid": user_id},
            ).fetchall()
        return [self.get(r[0]) for r in rows]

    def list_all(self) -> list[dict]:
        with get_db() as db:
            rows = db.execute(
                text("SELECT id FROM shop_orders ORDER BY created_at DESC")
            ).fetchall()
        return [self.get(r[0]) for r in rows]

    def attach_checkout_session(self, order_id: str, stripe_session_id: str) -> None:
        with get_db() as db:
            db.execute(
                text("UPDATE shop_orders SET stripe_session_id = :sid WHERE id = :id"),
                {"sid": stripe_session_id, "id": order_id},
            )

    def mark_paid(self, order_id: str, stripe_payment_intent_id: str | None,
                  shipping_address: dict | None) -> None:
        order = self._require_status(order_id, "pending_payment")
        shipping_address = shipping_address or {}
        with get_db() as db:
            db.execute(
                text("""
                    UPDATE shop_orders SET
                        status = 'paid', paid_at = :now,
                        stripe_payment_intent_id = :pi,
                        shipping_recipient_name = :name, shipping_line1 = :line1,
                        shipping_line2 = :line2, shipping_city = :city,
                        shipping_state = :state, shipping_postal_code = :postal,
                        shipping_country = :country
                    WHERE id = :id
                """),
                {
                    "now": _utcnow().isoformat(), "pi": stripe_payment_intent_id,
                    "name": shipping_address.get("name"), "line1": shipping_address.get("line1"),
                    "line2": shipping_address.get("line2"), "city": shipping_address.get("city"),
                    "state": shipping_address.get("state"), "postal": shipping_address.get("postal_code"),
                    "country": shipping_address.get("country"), "id": order_id,
                },
            )

    def mark_canceled(self, order_id: str) -> None:
        self._require_status(order_id, "pending_payment")
        with get_db() as db:
            db.execute(
                text("UPDATE shop_orders SET status = 'canceled' WHERE id = :id"),
                {"id": order_id},
            )

    def request_return(self, order_id: str, reason: str) -> None:
        order = self._require_status(order_id, "paid")
        paid_at = _parse_dt(order["paid_at"])
        if paid_at is not None and _utcnow() > paid_at + timedelta(days=RETURN_WINDOW_DAYS):
            raise InvalidOrderState(
                f"Return window ({RETURN_WINDOW_DAYS} days) has passed for this order"
            )
        with get_db() as db:
            db.execute(
                text(
                    "UPDATE shop_orders SET status = 'return_requested', "
                    "return_requested_at = :now, return_reason = :reason WHERE id = :id"
                ),
                {"now": _utcnow().isoformat(), "reason": reason, "id": order_id},
            )

    def approve_return(self, order_id: str) -> None:
        self._require_status(order_id, "return_requested")
        with get_db() as db:
            db.execute(
                text(
                    "UPDATE shop_orders SET status = 'returned', returned_at = :now WHERE id = :id"
                ),
                {"now": _utcnow().isoformat(), "id": order_id},
            )

    def _require_status(self, order_id: str, expected_status: str) -> dict:
        order = self.get(order_id)
        if not order:
            raise InvalidOrderState(f"Order {order_id} not found")
        if order["status"] != expected_status:
            raise InvalidOrderState(
                f"Order {order_id} is {order['status']}, expected {expected_status}"
            )
        return order

    @staticmethod
    def _effective(order: dict) -> dict:
        for field in ("created_at", "paid_at", "return_requested_at", "returned_at"):
            order[field] = _parse_dt(order.get(field))
        return order
