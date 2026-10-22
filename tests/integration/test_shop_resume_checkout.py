"""POST /shop/orders/{id}/resume-checkout[-guest]: getting back to a working
Stripe Checkout Session for a pending_payment order whose original checkout
link is gone (expired, lost, or the order was created in a past session) --
without re-touching stock or the cart, since the order already reserved
both. Ownership must be enforced: neither route may hand out a checkout URL
for an order that isn't the caller's."""
import uuid
from types import SimpleNamespace

import apps.omyfish_api.billing as billing_module
from apps.omyfish_api.repositories.order_repository import OrderRepository


def _stub_stripe_checkout(monkeypatch, next_id="cs_resumed"):
    def _create(**kwargs):
        return {"id": next_id, "url": f"https://stripe.test/checkout/{next_id}"}

    fake_stripe = SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=_create))
    )
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)


def _make_pending_order(client, monkeypatch, headers, guest_email=None):
    _stub_stripe_checkout(monkeypatch, next_id="cs_original")
    product = client.get("/shop/products").json()[0]
    client.post("/shop/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    body = {"success_url": "https://app/success", "cancel_url": "https://app/cancel"}
    if guest_email:
        body["guest_email"] = guest_email
    resp = client.post(
        "/shop/checkout", json=body,
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    return resp.json()["order_id"]


def test_resume_checkout_happy_path(client, monkeypatch, auth_headers):
    headers, user_id = auth_headers
    order_id = _make_pending_order(client, monkeypatch, headers)

    _stub_stripe_checkout(monkeypatch, next_id="cs_resumed")  # stored session isn't retrievable -> fresh one
    resp = client.post(
        f"/shop/orders/{order_id}/resume-checkout",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://stripe.test/checkout/cs_resumed"
    assert OrderRepository().get(order_id)["stripe_session_id"] == "cs_resumed"


def test_resume_checkout_rejects_another_users_order(client, monkeypatch, auth_headers):
    headers, _ = auth_headers
    order_id = _make_pending_order(client, monkeypatch, headers)

    client.post("/auth/register", json={"email": "other@example.com", "password": "pw123456"})
    other_token = client.post(
        "/auth/login", json={"email": "other@example.com", "password": "pw123456"}
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.post(
        f"/shop/orders/{order_id}/resume-checkout",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel"},
        headers=other_headers,
    )
    assert resp.status_code == 404


def test_resume_checkout_rejects_non_pending_order(client, monkeypatch, auth_headers):
    headers, user_id = auth_headers
    order_id = _make_pending_order(client, monkeypatch, headers)
    OrderRepository().mark_paid(order_id, "pi_test", {})

    resp = client.post(
        f"/shop/orders/{order_id}/resume-checkout",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_resume_checkout_guest_happy_path(client, monkeypatch):
    guest_headers = {"X-Cart-Token": str(uuid.uuid4())}
    order_id = _make_pending_order(client, monkeypatch, guest_headers, guest_email="guest@example.com")

    _stub_stripe_checkout(monkeypatch, next_id="cs_resumed_guest")
    resp = client.post(
        f"/shop/orders/{order_id}/resume-checkout-guest",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel",
              "email": "guest@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://stripe.test/checkout/cs_resumed_guest"


def test_resume_checkout_guest_rejects_wrong_email(client, monkeypatch):
    guest_headers = {"X-Cart-Token": str(uuid.uuid4())}
    order_id = _make_pending_order(client, monkeypatch, guest_headers, guest_email="guest@example.com")

    resp = client.post(
        f"/shop/orders/{order_id}/resume-checkout-guest",
        json={"success_url": "https://app/success", "cancel_url": "https://app/cancel",
              "email": "wrong@example.com"},
    )
    assert resp.status_code == 404
