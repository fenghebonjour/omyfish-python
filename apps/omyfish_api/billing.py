"""Stripe billing glue. All Stripe calls live here; routes and the
Streamlit UI call these functions. Returns None / raises BillingNotConfigured
when Stripe env vars are absent so the rest of the app works without them.
"""
from datetime import datetime, timezone
from typing import Optional

from apps.omyfish_api.repositories.webhook_event_repository import WebhookEventRepository
from shared.config import settings

PLANS = {
    "monthly": {"label": "5 CAD / month", "amount_cad": 5},
    "yearly": {"label": "29 CAD / year", "amount_cad": 29},
}

# Same timeout discipline as the Bite Score forecast's requests.get(timeout=...) call
# (apps/omyfish_web/timing.py) — a slow Stripe must never hang a request indefinitely.
# No retries: a failed charge/subscription-create must never be retried without the
# idempotency key already in place, so this is deliberately timeout-only.
CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 15


class BillingNotConfigured(Exception):
    pass


class RefundNotAvailable(Exception):
    pass


def _stripe():
    if not settings.stripe_secret_key:
        raise BillingNotConfigured("Set STRIPE_SECRET_KEY to enable billing.")
    import stripe
    stripe.api_key = settings.stripe_secret_key
    if stripe.default_http_client is None:
        stripe.default_http_client = stripe.RequestsClient(
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S)
        )
    return stripe


def _price_id(plan: str) -> str:
    price = {
        "monthly": settings.stripe_price_monthly,
        "yearly": settings.stripe_price_yearly,
    }.get(plan, "")
    if not price:
        raise BillingNotConfigured(f"Set the Stripe price id for the {plan} plan.")
    return price


def create_checkout_session(user_id: str, email: str, plan: str, idempotency_key: str) -> str:
    """Returns the Stripe Checkout URL for the given plan."""
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        client_reference_id=user_id,
        line_items=[{"price": _price_id(plan), "quantity": 1}],
        success_url=f"{settings.app_base_url}?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.app_base_url}?billing=canceled",
        metadata={"user_id": user_id, "plan": plan},
        idempotency_key=idempotency_key,
    )
    return session.url


def refund_subscription(stripe_subscription_id: str, idempotency_key: str,
                         amount_cents: Optional[int] = None) -> dict:
    """Refund the subscription's latest paid invoice (full, or partial via
    amount_cents). Local subscription status is left untouched — refunding
    is a separate explicit action from revoke."""
    stripe = _stripe()
    sub = stripe.Subscription.retrieve(
        stripe_subscription_id,
        expand=["latest_invoice.payments.data.payment.payment_intent"],
    )
    invoice = sub.get("latest_invoice") or {}
    payments = (invoice.get("payments") or {}).get("data") or []
    payment_intent_id = None
    if payments:
        payment = payments[0].get("payment") or {}
        pi = payment.get("payment_intent")
        payment_intent_id = pi["id"] if isinstance(pi, dict) else pi
    if not payment_intent_id:
        raise RefundNotAvailable("No paid invoice to refund for this subscription.")

    params = {"payment_intent": payment_intent_id, "idempotency_key": idempotency_key}
    if amount_cents is not None:
        params["amount"] = amount_cents
    refund = stripe.Refund.create(**params)
    return {"refund_id": refund.id, "status": refund.status, "amount": refund.amount}


def list_recent_subscriptions(since: datetime) -> list[dict]:
    """List Stripe subscriptions created since `since`, for reconciliation.
    Every subscription created via create_checkout_session carries user_id/plan
    in its metadata; a subscription missing that metadata isn't ours and is
    skipped."""
    stripe = _stripe()
    candidates = []
    subs = stripe.Subscription.list(created={"gte": int(since.timestamp())}, limit=100)
    for sub in subs.auto_paging_iter():
        metadata = sub.get("metadata") or {}
        user_id = metadata.get("user_id")
        if not user_id:
            continue
        candidates.append({
            "user_id": user_id,
            "plan": metadata.get("plan"),
            "stripe_customer_id": sub.get("customer"),
            "stripe_subscription_id": sub.get("id"),
            "status": sub.get("status"),
            "current_period_end": sub.get("current_period_end"),
        })
    return candidates


def reconcile(since: datetime, repo) -> dict:
    """Repair local subscription rows whose Stripe link is missing or
    mismatched (e.g. the process crashed between the Stripe call succeeding
    and the local row being saved), then resync status/period_end from the
    same data. One bad candidate is skipped rather than aborting the rest."""
    repaired = resynced = skipped = 0
    for candidate in list_recent_subscriptions(since):
        try:
            user_id = candidate["user_id"]
            current = repo.get_for_user(user_id) or repo.start_trial(user_id)
            linked = (
                current.get("stripe_customer_id") == candidate["stripe_customer_id"]
                and current.get("stripe_subscription_id") == candidate["stripe_subscription_id"]
            )
            if not linked:
                repaired += 1

            if candidate["status"] in ("canceled", "unpaid", "incomplete_expired"):
                repo.set_status(user_id, "canceled")
            else:
                period_end = candidate["current_period_end"]
                repo.set_active(
                    user_id,
                    plan=candidate.get("plan") or current.get("plan") or "monthly",
                    period_end=datetime.fromtimestamp(period_end, tz=timezone.utc)
                    if period_end else None,
                    stripe_customer_id=candidate["stripe_customer_id"],
                    stripe_subscription_id=candidate["stripe_subscription_id"],
                )
            resynced += 1
        except Exception:
            skipped += 1
    return {"repaired": repaired, "resynced": resynced, "skipped": skipped}


def verify_webhook(payload: bytes, signature: str):
    """Returns the verified Stripe event or raises."""
    stripe = _stripe()
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured("Set STRIPE_WEBHOOK_SECRET to enable the webhook.")
    return stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)


def apply_event(event: dict, repo) -> Optional[str]:
    """Map a Stripe event onto subscription state. Returns the affected
    user_id (or None if the event type is ignored). Stripe can and does
    redeliver webhooks; a redelivered event id short-circuits here instead
    of reapplying it."""
    event_id = event.get("id")
    events_repo = WebhookEventRepository()
    if event_id and events_repo.already_processed(event_id):
        return event_id

    result = _apply_event_effects(event, repo)

    if event_id and result is not None:
        events_repo.mark_processed(event_id)
    return result


def _activate_from_checkout_session(obj: dict, repo) -> Optional[str]:
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


def confirm_checkout_session(session_id: str, repo) -> Optional[str]:
    """Synchronous fallback for deployments with no reachable webhook endpoint
    (BACKLOG.md item C, step 1): retrieve the Checkout Session directly and
    apply the same activation `checkout.session.completed` would have.
    Dedup is keyed off the session id (not a webhook event id) since the
    caller — Streamlit, on the page load the success_url redirects back to —
    may call this again on a later rerun of the same load."""
    stripe = _stripe()
    session = stripe.checkout.Session.retrieve(session_id)
    if session.get("status") != "complete":
        return None

    dedup_key = f"checkout_session:{session_id}"
    events_repo = WebhookEventRepository()
    if events_repo.already_processed(dedup_key):
        return session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")

    user_id = _activate_from_checkout_session(session, repo)
    if user_id:
        events_repo.mark_processed(dedup_key)
    return user_id


def _apply_event_effects(event: dict, repo) -> Optional[str]:
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        return _activate_from_checkout_session(obj, repo)

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
