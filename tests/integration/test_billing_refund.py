"""Admin refund endpoint (Stripe calls stubbed)."""
from datetime import datetime, timedelta, timezone

import apps.omyfish_api.billing as billing_module
from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository
from shared.config import settings


def _register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["boss@example.com"])
    return _register_and_login(client, "boss@example.com")


def _with_stripe_subscription(user_id: str) -> None:
    repo = SubscriptionRepository()
    repo.set_active(
        user_id, plan="monthly",
        period_end=datetime.now(timezone.utc) + timedelta(days=30),
        stripe_customer_id="cus_test123",
        stripe_subscription_id="sub_test123",
    )


def test_admin_refund_requires_admin(client):
    headers = _register_and_login(client, "angler@example.com")
    r = client.post(
        f"/admin/subscriptions/{'whatever'}/refund",
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 403


def test_admin_refund_404_without_subscription(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    r = client.post(
        "/admin/subscriptions/does-not-exist/refund",
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 404


def test_admin_refund_400_without_stripe_subscription(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]

    r = client.post(
        f"/admin/subscriptions/{target}/refund",
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 400


def test_admin_refund_success(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]
    _with_stripe_subscription(target)

    monkeypatch.setattr(
        billing_module, "refund_subscription",
        lambda sub_id, idem_key, amount_cents=None: {
            "refund_id": "re_123", "status": "succeeded", "amount": 500,
        },
    )
    r = client.post(
        f"/admin/subscriptions/{target}/refund",
        json={"amount_cents": 500},
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 200
    assert r.json() == {"refund_id": "re_123", "status": "succeeded", "amount": 500}


def test_admin_refund_no_invoice_returns_400(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]
    _with_stripe_subscription(target)

    def _boom(sub_id, idem_key, amount_cents=None):
        raise billing_module.RefundNotAvailable("No paid invoice to refund for this subscription.")

    monkeypatch.setattr(billing_module, "refund_subscription", _boom)
    r = client.post(
        f"/admin/subscriptions/{target}/refund",
        headers={**headers, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 400


def test_admin_refund_replays_for_same_key(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]
    _with_stripe_subscription(target)

    calls = []

    def _stub(sub_id, idem_key, amount_cents=None):
        calls.append(1)
        return {"refund_id": "re_123", "status": "succeeded", "amount": 500}

    monkeypatch.setattr(billing_module, "refund_subscription", _stub)
    idem_headers = {**headers, "Idempotency-Key": "same-refund-key"}
    r1 = client.post(f"/admin/subscriptions/{target}/refund", headers=idem_headers)
    r2 = client.post(f"/admin/subscriptions/{target}/refund", headers=idem_headers)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert len(calls) == 1
