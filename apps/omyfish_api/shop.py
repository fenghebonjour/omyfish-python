"""Omyshop: one-time-purchase product catalog, cart, checkout, orders, and
returns/refunds — separate from billing.py's subscription flow (own Stripe
checkout mode, own webhook endpoint/secret). Ported from omyfish-java's
shop-service, re-expressed in this repo's flat-module/raw-SQL conventions
instead of its hexagonal ports-and-adapters architecture.
"""
from datetime import datetime, timezone
from typing import Optional

from apps.omyfish_api import billing
from apps.omyfish_api.billing import BillingNotConfigured
from apps.omyfish_api.repositories.cart_repository import CartRepository
from apps.omyfish_api.repositories.order_repository import InvalidOrderState, OrderRepository
from apps.omyfish_api.repositories.product_repository import ProductRepository
from apps.omyfish_api.repositories.webhook_event_repository import WebhookEventRepository
from apps.omyfish_api.stripe_utils import as_dict
from shared.config import settings

CURRENCY = "cad"
SHIPPING_ALLOWED_COUNTRIES = ["CA"]


class CartEmptyException(Exception):
    pass


class InsufficientStockException(Exception):
    pass


# ── Cart ──────────────────────────────────────────────────────────────────────

def get_cart_with_items(user_id: Optional[str] = None, guest_token: Optional[str] = None) -> dict:
    cart = CartRepository().get_or_create(user_id=user_id, guest_token=guest_token)
    items = CartRepository().get_items(cart["id"])
    products = ProductRepository()
    enriched = []
    for item in items:
        product = products.get(item["product_id"])
        if product:
            enriched.append({**item, "product": product})
    cart["items"] = enriched
    return cart


def add_to_cart(product_id: str, quantity: int,
                 user_id: Optional[str] = None, guest_token: Optional[str] = None) -> dict:
    cart = CartRepository().get_or_create(user_id=user_id, guest_token=guest_token)
    CartRepository().add_item(cart["id"], product_id, quantity)
    return get_cart_with_items(user_id=user_id, guest_token=guest_token)


def update_cart_item(product_id: str, quantity: int,
                      user_id: Optional[str] = None, guest_token: Optional[str] = None) -> dict:
    cart = CartRepository().get_or_create(user_id=user_id, guest_token=guest_token)
    CartRepository().set_quantity(cart["id"], product_id, quantity)
    return get_cart_with_items(user_id=user_id, guest_token=guest_token)


def merge_guest_cart(user_id: str, guest_token: str) -> dict:
    return CartRepository().merge_guest_into_user(user_id, guest_token)


# ── Checkout ──────────────────────────────────────────────────────────────────

def checkout(success_url: str, cancel_url: str, idempotency_key: str,
             user_id: Optional[str] = None, guest_token: Optional[str] = None,
             guest_email: Optional[str] = None) -> dict:
    """Reserves stock + creates a pending_payment order BEFORE the Stripe call
    (same ordering as omyfish-java's ReserveOrderService), then creates a
    Stripe Checkout Session. A Stripe-call failure compensates by canceling
    the order and restocking every line, mirroring the Java cancelAndRestock
    path. Returns {"order_id", "checkout_url"}."""
    stripe = billing._stripe()  # raises BillingNotConfigured if unset

    cart = CartRepository().get_or_create(user_id=user_id, guest_token=guest_token)
    cart_items = CartRepository().get_items(cart["id"])
    if not cart_items:
        raise CartEmptyException("Cart is empty")

    products = ProductRepository()
    lines = []
    total_cents = 0
    for item in cart_items:
        product = products.get(item["product_id"])
        if not product or product["stock_quantity"] < item["quantity"]:
            raise InsufficientStockException(
                f"Not enough stock for product {item['product_id']}"
            )
        lines.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "unit_price_cents": product["price_cents"],
            "quantity": item["quantity"],
        })
        total_cents += product["price_cents"] * item["quantity"]

    for line in lines:
        products.decrease_stock(line["product_id"], line["quantity"])

    orders = OrderRepository()
    order_id = orders.create_pending(user_id, guest_email, lines, total_cents)
    CartRepository().clear(cart["id"])

    try:
        session = as_dict(stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": CURRENCY,
                    "product_data": {"name": line["product_name"]},
                    "unit_amount": line["unit_price_cents"],
                },
                "quantity": line["quantity"],
            } for line in lines],
            shipping_address_collection={"allowed_countries": SHIPPING_ALLOWED_COUNTRIES},
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=guest_email,
            client_reference_id=order_id,
            idempotency_key=idempotency_key,
        ))
    except Exception:
        _cancel_and_restock(order_id)
        raise

    orders.attach_checkout_session(order_id, session["id"])
    return {"order_id": order_id, "checkout_url": session["url"]}


def _cancel_and_restock(order_id: str) -> None:
    orders = OrderRepository()
    order = orders.get(order_id)
    orders.mark_canceled(order_id)
    products = ProductRepository()
    for line in order["lines"]:
        products.restock(line["product_id"], line["quantity"])


def confirm_shop_checkout_session(session_id: str) -> Optional[str]:
    """Synchronous fallback mirroring billing.confirm_checkout_session — a
    backstop for a webhook delayed by Render free-tier cold start. Dedup
    keyed off the session id (not a webhook event id), same pattern."""
    stripe = billing._stripe()
    session = as_dict(stripe.checkout.Session.retrieve(session_id))
    if session.get("status") != "complete":
        return None

    dedup_key = f"shop_checkout_session:{session_id}"
    events_repo = WebhookEventRepository()
    order = OrderRepository().get_by_stripe_session(session_id)
    if not order:
        return None
    if events_repo.already_processed(dedup_key):
        return order["id"]

    if order["status"] == "pending_payment":
        OrderRepository().mark_paid(
            order["id"], session.get("payment_intent"), _extract_shipping(session)
        )
    events_repo.mark_processed(dedup_key)
    return order["id"]


# ── Webhook ───────────────────────────────────────────────────────────────────

def verify_shop_webhook(payload: bytes, signature: str):
    stripe = billing._stripe()
    if not settings.stripe_shop_webhook_secret:
        raise BillingNotConfigured("Set STRIPE_SHOP_WEBHOOK_SECRET to enable the shop webhook.")
    return as_dict(stripe.Webhook.construct_event(
        payload, signature, settings.stripe_shop_webhook_secret
    ))


def apply_shop_event(event: dict) -> Optional[str]:
    """Mirrors billing.apply_event: dedups on Stripe's event id via the same
    shared WebhookEventRepository (event ids are globally unique per Stripe
    account regardless of which endpoint receives them)."""
    event_id = event.get("id")
    events_repo = WebhookEventRepository()
    if event_id and events_repo.already_processed(event_id):
        return event_id

    result = _apply_shop_event_effects(event)

    if event_id and result is not None:
        events_repo.mark_processed(event_id)
    return result


def _apply_shop_event_effects(event: dict) -> Optional[str]:
    etype = event["type"]
    session = event["data"]["object"]

    if etype == "checkout.session.completed":
        order = OrderRepository().get_by_stripe_session(session.get("id"))
        if not order or order["status"] != "pending_payment":
            return None
        OrderRepository().mark_paid(
            order["id"], session.get("payment_intent"), _extract_shipping(session)
        )
        return order["id"]

    if etype == "checkout.session.expired":
        order = OrderRepository().get_by_stripe_session(session.get("id"))
        if not order or order["status"] != "pending_payment":
            return None
        _cancel_and_restock(order["id"])
        return order["id"]

    return None


def _extract_shipping(session: dict) -> dict:
    """Stripe moved shipping details under collected_information in newer API
    versions; fall back to the older top-level key for safety."""
    shipping = (session.get("collected_information") or {}).get("shipping_details") \
        or session.get("shipping_details") or {}
    address = shipping.get("address") or {}
    return {
        "name": shipping.get("name"),
        "line1": address.get("line1"),
        "line2": address.get("line2"),
        "city": address.get("city"),
        "state": address.get("state"),
        "postal_code": address.get("postal_code"),
        "country": address.get("country"),
    }


# ── Returns / refunds ─────────────────────────────────────────────────────────

def request_return(order_id: str, user_id: str, reason: str) -> None:
    order = OrderRepository().get(order_id)
    if not order or order.get("user_id") != user_id:
        raise InvalidOrderState(f"Order {order_id} not found")
    OrderRepository().request_return(order_id, reason)


def approve_return(order_id: str, idempotency_key: str) -> dict:
    """Admin-only. Issues a Stripe refund for the full order total, then
    restocks every line and marks the order returned."""
    order = OrderRepository().get(order_id)
    if not order:
        raise InvalidOrderState(f"Order {order_id} not found")
    if not order.get("stripe_payment_intent_id"):
        raise InvalidOrderState(f"Order {order_id} has no Stripe payment to refund")

    stripe = billing._stripe()
    refund = as_dict(stripe.Refund.create(
        payment_intent=order["stripe_payment_intent_id"],
        amount=order["total_cents"],
        idempotency_key=idempotency_key,
    ))

    OrderRepository().approve_return(order_id)
    products = ProductRepository()
    for line in order["lines"]:
        products.restock(line["product_id"], line["quantity"])

    return {"refund_id": refund["id"], "status": refund["status"], "amount": refund["amount"]}
