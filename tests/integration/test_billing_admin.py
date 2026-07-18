"""Billing lifecycle + admin endpoints (Stripe never called — unconfigured
paths and direct event application only)."""
from datetime import datetime, timedelta, timezone

from apps.omyfish_api import billing
from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository
from shared.config import settings


def _register_and_login(client, email="sub@example.com", admin=False):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Trial lifecycle ───────────────────────────────────────────────────────────

def test_register_starts_seven_day_trial(client):
    headers = _register_and_login(client)
    me = client.get("/billing/me", headers=headers).json()
    assert me["status"] == "trialing"
    trial_end = datetime.fromisoformat(me["trial_end"])
    days = (trial_end - datetime.now(timezone.utc)).total_seconds() / 86400
    assert 6.9 < days <= 7.0


def test_expired_trial_reads_as_expired(client):
    headers = _register_and_login(client)
    me = client.get("/auth/me", headers=headers).json()
    repo = SubscriptionRepository()
    from apps.omyfish_api.db.engine import get_db
    from sqlalchemy import text
    with get_db() as db:
        db.execute(
            text("UPDATE subscriptions SET trial_end = :te WHERE user_id = :uid"),
            {"te": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
             "uid": me["id"]},
        )
    assert client.get("/billing/me", headers=headers).json()["status"] == "expired"


def test_checkout_returns_503_when_stripe_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    headers = _register_and_login(client)
    r = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
    assert r.status_code == 503


def test_checkout_rejects_unknown_plan(client):
    headers = _register_and_login(client)
    r = client.post("/billing/checkout", json={"plan": "weekly"}, headers=headers)
    assert r.status_code == 400


def test_billing_requires_auth(client):
    assert client.get("/billing/me").status_code == 401
    assert client.post("/billing/checkout", json={"plan": "monthly"}).status_code == 401


# ── Stripe event application (no network) ─────────────────────────────────────

def _checkout_completed(user_id, plan="yearly"):
    return {
        "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": user_id,
            "customer": "cus_test123",
            "subscription": "sub_test123",
            "metadata": {"user_id": user_id, "plan": plan},
        }},
    }


def test_checkout_completed_event_activates_subscription(client):
    headers = _register_and_login(client)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    repo = SubscriptionRepository()

    billing.apply_event(_checkout_completed(user_id), repo)
    me = client.get("/billing/me", headers=headers).json()
    assert me["status"] == "active" and me["plan"] == "yearly"


def test_subscription_deleted_event_cancels(client):
    headers = _register_and_login(client)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    repo = SubscriptionRepository()
    billing.apply_event(_checkout_completed(user_id), repo)

    billing.apply_event({
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_test123", "id": "sub_test123"}},
    }, repo)
    assert client.get("/billing/me", headers=headers).json()["status"] == "canceled"


def test_unknown_event_type_ignored(client):
    assert billing.apply_event(
        {"type": "invoice.paid", "data": {"object": {}}}, SubscriptionRepository()
    ) is None


# ── Admin ─────────────────────────────────────────────────────────────────────

def _admin_headers(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["boss@example.com"])
    return _register_and_login(client, email="boss@example.com")


def test_admin_endpoints_are_admin_only(client):
    headers = _register_and_login(client)
    assert client.get("/admin/stats").status_code == 401
    assert client.get("/admin/stats", headers=headers).status_code == 403


def test_admin_emails_get_admin_role(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    assert client.get("/auth/me", headers=headers).json()["role"] == "admin"


def test_admin_stats_and_subscriptions(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    _register_and_login(client, email="angler2@example.com")

    stats = client.get("/admin/stats", headers=headers).json()
    assert stats["users"] == 2
    assert stats["subscriptions"]["trialing"] == 2
    assert stats["mrr_cad"] == 0

    subs = client.get("/admin/subscriptions", headers=headers).json()
    assert {s["email"] for s in subs} == {"boss@example.com", "angler2@example.com"}


def test_admin_grant_and_revoke(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    _register_and_login(client, email="angler2@example.com")
    target = next(
        u["id"] for u in client.get("/users", headers=headers).json()
        if u["email"] == "angler2@example.com"
    )

    granted = client.post(
        f"/admin/subscriptions/{target}/grant", json={"days": 30, "plan": "monthly"},
        headers=headers,
    ).json()
    assert granted["status"] == "active" and granted["plan"] == "monthly"

    stats = client.get("/admin/stats", headers=headers).json()
    assert stats["mrr_cad"] == 5.0

    revoked = client.post(f"/admin/subscriptions/{target}/revoke", headers=headers).json()
    assert revoked["status"] == "canceled"


def test_admin_extend_trial(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    me = client.get("/auth/me", headers=headers).json()

    extended = client.post(
        f"/admin/users/{me['id']}/extend-trial", json={"days": 7}, headers=headers
    ).json()
    trial_end = datetime.fromisoformat(extended["trial_end"])
    days = (trial_end - datetime.now(timezone.utc)).total_seconds() / 86400
    assert 13.9 < days <= 14.0
