"""Webhook event-id dedup in billing.apply_event (Stripe redelivers events)."""
from apps.omyfish_api import billing
from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository
from apps.omyfish_api.repositories.webhook_event_repository import WebhookEventRepository


def _register_and_login(client, email="sub@example.com"):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_duplicate_webhook_event_id_is_not_reprocessed(client):
    headers = _register_and_login(client)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    repo = SubscriptionRepository()

    event = {
        "id": "evt_123",
        "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": user_id,
            "customer": "cus_test123",
            "subscription": "sub_test123",
            "metadata": {"user_id": user_id, "plan": "monthly"},
        }},
    }
    billing.apply_event(event, repo)

    # Same event id redelivered, now claiming a different plan — if dedup
    # works this redelivery must not overwrite the already-stored plan.
    redelivered = {
        **event,
        "data": {"object": {**event["data"]["object"],
                             "metadata": {"user_id": user_id, "plan": "yearly"}}},
    }
    billing.apply_event(redelivered, repo)

    me = client.get("/billing/me", headers=headers).json()
    assert me["plan"] == "monthly"


def test_unhandled_event_type_is_not_recorded_for_dedup(client):
    repo = SubscriptionRepository()
    event = {"id": "evt_456", "type": "invoice.paid", "data": {"object": {}}}
    assert billing.apply_event(event, repo) is None
    assert WebhookEventRepository().already_processed("evt_456") is False


def test_event_without_id_is_still_applied_each_time(client):
    """Older-shaped events (no id) have nothing to dedup against — this
    only matters for malformed/test events, real Stripe events always have one."""
    headers = _register_and_login(client)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    repo = SubscriptionRepository()

    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": user_id,
            "customer": "cus_test123",
            "subscription": "sub_test123",
            "metadata": {"user_id": user_id, "plan": "monthly"},
        }},
    }
    assert billing.apply_event(event, repo) == user_id
