"""30-day return window, admin approval, and the Stripe refund + restock
that approval triggers."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import apps.omyfish_api.billing as billing_module
from apps.omyfish_api.db.engine import get_db
from apps.omyfish_api.repositories.order_repository import OrderRepository
from apps.omyfish_api.repositories.product_repository import ProductRepository
from shared.config import settings
from sqlalchemy import text


def _register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["boss@example.com"])
    return _register_and_login(client, "boss@example.com")


def _paid_order(client, user_id, product, paid_at: datetime):
    ProductRepository().decrease_stock(product["id"], 1)
    order_id = OrderRepository().create_pending(
        user_id, None,
        [{"product_id": product["id"], "product_name": product["name"],
          "unit_price_cents": product["price_cents"], "quantity": 1}],
        product["price_cents"],
    )
    with get_db() as db:
        db.execute(
            text(
                "UPDATE shop_orders SET status = 'paid', paid_at = :pa, "
                "stripe_payment_intent_id = 'pi_test_return' WHERE id = :id"
            ),
            {"pa": paid_at.isoformat(), "id": order_id},
        )
    return order_id


def _stub_refund(monkeypatch):
    fake_stripe = SimpleNamespace(
        Refund=SimpleNamespace(
            create=lambda **kw: {"id": "re_test_1", "status": "succeeded", "amount": kw["amount"]}
        )
    )
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)


def test_return_within_window_succeeds(client):
    headers = _register_and_login(client, "returner@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    product = client.get("/shop/products").json()[0]
    order_id = _paid_order(client, user_id, product, datetime.now(timezone.utc) - timedelta(days=5))

    resp = client.post(f"/shop/orders/{order_id}/returns", json={"reason": "wrong size"},
                        headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "return_requested"


def test_return_past_window_rejected(client):
    headers = _register_and_login(client, "latereturner@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    product = client.get("/shop/products").json()[0]
    order_id = _paid_order(client, user_id, product, datetime.now(timezone.utc) - timedelta(days=31))

    resp = client.post(f"/shop/orders/{order_id}/returns", json={"reason": "too late"},
                        headers=headers)
    assert resp.status_code == 409


def test_admin_approve_return_refunds_and_restocks(client, monkeypatch):
    _stub_refund(monkeypatch)
    user_headers = _register_and_login(client, "returner2@example.com")
    user_id = client.get("/auth/me", headers=user_headers).json()["id"]
    product = client.get("/shop/products").json()[0]
    before_stock = ProductRepository().get(product["id"])["stock_quantity"]
    order_id = _paid_order(client, user_id, product, datetime.now(timezone.utc) - timedelta(days=1))
    client.post(f"/shop/orders/{order_id}/returns", json={"reason": "defective"}, headers=user_headers)

    admin_headers = _admin_headers(client, monkeypatch)

    resp = client.patch(
        f"/admin/shop/orders/{order_id}/approve-return",
        headers={**admin_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"

    order = OrderRepository().get(order_id)
    assert order["status"] == "returned"
    remaining = ProductRepository().get(product["id"])
    assert remaining["stock_quantity"] == before_stock  # decremented then restocked: net zero
