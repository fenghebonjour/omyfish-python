"""Stripe billing glue. All Stripe calls live here; routes and the
Streamlit UI call these functions. Returns None / raises BillingNotConfigured
when Stripe env vars are absent so the rest of the app works without them.
"""
from datetime import datetime, timezone
from typing import Optional

from shared.config import settings

PLANS = {
    "monthly": {"label": "5 CAD / month", "amount_cad": 5},
    "yearly": {"label": "29 CAD / year", "amount_cad": 29},
}


class BillingNotConfigured(Exception):
    pass


def _stripe():
    if not settings.stripe_secret_key:
        raise BillingNotConfigured("Set STRIPE_SECRET_KEY to enable billing.")
    import stripe
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _price_id(plan: str) -> str:
    price = {
        "monthly": settings.stripe_price_monthly,
        "yearly": settings.stripe_price_yearly,
    }.get(plan, "")
    if not price:
        raise BillingNotConfigured(f"Set the Stripe price id for the {plan} plan.")
    return price


def create_checkout_session(user_id: str, email: str, plan: str) -> str:
    """Returns the Stripe Checkout URL for the given plan."""
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        client_reference_id=user_id,
        line_items=[{"price": _price_id(plan), "quantity": 1}],
        success_url=f"{settings.app_base_url}?billing=success",
        cancel_url=f"{settings.app_base_url}?billing=canceled",
        metadata={"user_id": user_id, "plan": plan},
    )
    return session.url


def verify_webhook(payload: bytes, signature: str):
    """Returns the verified Stripe event or raises."""
    stripe = _stripe()
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured("Set STRIPE_WEBHOOK_SECRET to enable the webhook.")
    return stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)


def apply_event(event: dict, repo) -> Optional[str]:
    """Map a Stripe event onto subscription state. Returns the affected
    user_id (or None if the event type is ignored)."""
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id")
        if not user_id:
            return None
        repo.set_active(
            user_id,
            plan=(obj.get("metadata") or {}).get("plan", "monthly"),
            period_end=None,  # authoritative period end arrives on subscription.updated
            stripe_customer_id=obj.get("customer"),
            stripe_subscription_id=obj.get("subscription"),
        )
        return user_id

    if etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        user_id = repo.find_user_by_stripe_customer(obj.get("customer"))
        if not user_id:
            return None
        if etype == "customer.subscription.deleted" or obj.get("status") in ("canceled", "unpaid"):
            repo.set_status(user_id, "canceled")
        else:
            period_end = obj.get("current_period_end")
            repo.set_active(
                user_id,
                plan=repo.get_for_user(user_id).get("plan") or "monthly",
                period_end=datetime.fromtimestamp(period_end, tz=timezone.utc)
                if period_end else None,
                stripe_subscription_id=obj.get("id"),
            )
        return user_id

    return None
