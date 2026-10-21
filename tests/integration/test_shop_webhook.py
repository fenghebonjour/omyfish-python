"""Shop Stripe webhook: checkout.session.completed marks an order paid,
checkout.session.expired cancels + restocks, redelivery is deduped (shared
WebhookEventRepository with the subscription webhook), and an invalid
signature is rejected."""
import uuid
from types import SimpleNamespace

import apps.omyfish_api.billing as billing_module
import apps.omyfish_api.shop as shop_module
from apps.omyfish_api.repositories.order_repository import OrderRepository
from apps.omyfish_api.repositories.product_repository import ProductRepository


def _stub_stripe_webhook(monkeypatch, event: dict):
    fake_stripe = SimpleNamespace(
        Webhook=SimpleNamespace(construct_event=lambda payload, sig, secret: event)
    )
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)


def _create_pending_order(product):
    ProductRepository().decrease_stock(product["id"], 2)
    order_id = OrderRepository().create_pending(
        None, "guest@example.com",
        [{"product_id": product["id"], "product_name": product["name"],
          "unit_price_cents": product["price_cents"], "quantity": 2}],
        product["price_cents"] * 2,
    )
    OrderRepository().attach_checkout_session(order_id, "cs_test_webhook")
    return order_id


def test_checkout_completed_marks_order_paid(client, monkeypatch):
    product = client.get("/shop/products").json()[0]
    order_id = _create_pending_order(product)

    event = {
        "id": "evt_test_1", "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_webhook", "payment_intent": "pi_test_123",
            "collected_information": {"shipping_details": {
                "name": "Jane Angler",
                "address": {"line1": "1 Lake Rd", "line2": None, "city": "Québec",
                            "state": "QC", "postal_code": "G1A 1A1", "country": "CA"},
            }},
        }},
    }
    _stub_stripe_webhook(monkeypatch, event)
    monkeypatch.setattr("shared.config.settings.stripe_shop_webhook_secret", "whsec_test")

    resp = client.post("/shop/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert resp.status_code == 200
    assert resp.json()["handled"] is True

    order = OrderRepository().get(order_id)
    assert order["status"] == "paid"
    assert order["stripe_payment_intent_id"] == "pi_test_123"
    assert order["shipping_recipient_name"] == "Jane Angler"
    assert order["shipping_city"] == "Québec"


def test_checkout_expired_cancels_and_restocks(client, monkeypatch):
    product = client.get("/shop/products").json()[0]
    before_stock = product["stock_quantity"]
    order_id = _create_pending_order(product)

    event = {
        "id": "evt_test_2", "type": "checkout.session.expired",
        "data": {"object": {"id": "cs_test_webhook"}},
    }
    _stub_stripe_webhook(monkeypatch, event)
    monkeypatch.setattr("shared.config.settings.stripe_shop_webhook_secret", "whsec_test")

    resp = client.post("/shop/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert resp.status_code == 200

    order = OrderRepository().get(order_id)
    assert order["status"] == "canceled"
    remaining = ProductRepository().get(product["id"])
    assert remaining["stock_quantity"] == before_stock  # restocked


def test_duplicate_event_id_is_not_reprocessed(client, monkeypatch):
    product = client.get("/shop/products").json()[0]
    order_id = _create_pending_order(product)

    event = {
        "id": "evt_test_dup", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_webhook", "payment_intent": "pi_test_dup"}},
    }
    assert shop_module.apply_shop_event(event) == order_id
    # Second application of the same event id is a no-op even though the
    # order is no longer pending_payment (it already flipped to paid).
    assert shop_module.apply_shop_event(event) == "evt_test_dup"


def test_invalid_signature_rejected(client, monkeypatch):
    def _raise(*a, **kw):
        raise ValueError("bad signature")

    fake_stripe = SimpleNamespace(Webhook=SimpleNamespace(construct_event=_raise))
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)
    monkeypatch.setattr("shared.config.settings.stripe_shop_webhook_secret", "whsec_test")

    resp = client.post("/shop/webhook", content=b"{}", headers={"stripe-signature": "bad"})
    assert resp.status_code == 400
