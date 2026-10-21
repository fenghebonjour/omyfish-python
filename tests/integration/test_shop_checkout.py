"""One-time Stripe checkout: stock reservation ordering, empty-cart and
insufficient-stock rejection, and compensation (cancel + restock) when the
Stripe call itself fails."""
import uuid
from types import SimpleNamespace

import pytest

import apps.omyfish_api.billing as billing_module
import apps.omyfish_api.shop as shop_module
from apps.omyfish_api.repositories.order_repository import OrderRepository
from apps.omyfish_api.repositories.product_repository import ProductRepository


def _stub_stripe_checkout(monkeypatch, session: dict | None = None, raise_on_create=False):
    def _create(**kwargs):
        if raise_on_create:
            raise RuntimeError("Stripe is down")
        return session or {"id": "cs_test_abc", "url": "https://stripe.test/checkout/cs_test_abc"}

    fake_stripe = SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=_create))
    )
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)


def _guest_headers():
    return {"X-Cart-Token": str(uuid.uuid4())}


def test_checkout_rejects_empty_cart(client, monkeypatch):
    _stub_stripe_checkout(monkeypatch)
    resp = client.post(
        "/shop/checkout",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel",
              "guest_email": "guest@example.com"},
        headers={**_guest_headers(), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


def test_checkout_happy_path_decrements_stock_and_clears_cart(client, monkeypatch):
    _stub_stripe_checkout(monkeypatch)
    product = client.get("/shop/products").json()[0]
    headers = _guest_headers()
    client.post("/shop/cart/items", json={"product_id": product["id"], "quantity": 2}, headers=headers)

    resp = client.post(
        "/shop/checkout",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel",
              "guest_email": "guest@example.com"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["checkout_url"] == "https://stripe.test/checkout/cs_test_abc"

    order = OrderRepository().get(body["order_id"])
    assert order["status"] == "pending_payment"
    assert order["stripe_session_id"] == "cs_test_abc"
    assert len(order["lines"]) == 1 and order["lines"][0]["quantity"] == 2

    remaining = ProductRepository().get(product["id"])
    assert remaining["stock_quantity"] == product["stock_quantity"] - 2

    cart = client.get("/shop/cart", headers=headers).json()
    assert cart["items"] == []


def test_checkout_rejects_insufficient_stock(client, monkeypatch):
    _stub_stripe_checkout(monkeypatch)
    product = client.get("/shop/products").json()[0]
    headers = _guest_headers()
    client.post(
        "/shop/cart/items",
        json={"product_id": product["id"], "quantity": product["stock_quantity"] + 1},
        headers=headers,
    )
    resp = client.post(
        "/shop/checkout",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel",
              "guest_email": "guest@example.com"},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400
    remaining = ProductRepository().get(product["id"])
    assert remaining["stock_quantity"] == product["stock_quantity"]  # untouched


def test_checkout_stripe_failure_cancels_and_restocks(client, monkeypatch):
    # Calls shop.checkout() directly (not through the HTTP layer) to test the
    # compensation logic itself, same style as test_billing_checkout_confirm.py
    # calling billing.confirm_checkout_session() directly.
    _stub_stripe_checkout(monkeypatch, raise_on_create=True)
    product = client.get("/shop/products").json()[0]
    guest_token = str(uuid.uuid4())
    headers = {"X-Cart-Token": guest_token}
    client.post("/shop/cart/items", json={"product_id": product["id"], "quantity": 2}, headers=headers)

    with pytest.raises(RuntimeError, match="Stripe is down"):
        shop_module.checkout(
            success_url="https://app/success", cancel_url="https://app/cancel",
            idempotency_key=str(uuid.uuid4()), guest_token=guest_token,
            guest_email="guest@example.com",
        )

    remaining = ProductRepository().get(product["id"])
    assert remaining["stock_quantity"] == product["stock_quantity"]  # restocked
