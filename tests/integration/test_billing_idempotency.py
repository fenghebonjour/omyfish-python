"""Idempotency-Key handling on /billing/checkout (Stripe calls stubbed)."""
import apps.omyfish_api.billing as billing_module
from apps.omyfish_api.repositories.idempotency_repository import IdempotencyRepository


def _register_and_login(client, email="sub@example.com"):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_checkout_replays_stored_result_for_same_key(client, monkeypatch):
    calls = []

    def _stub(*args, **kwargs):
        calls.append(1)
        return "https://stripe.test/session/1"

    monkeypatch.setattr(billing_module, "create_checkout_session", _stub)
    headers = _register_and_login(client)
    headers["Idempotency-Key"] = "same-key"

    r1 = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
    r2 = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json() == {"checkout_url": "https://stripe.test/session/1"}
    assert len(calls) == 1


def test_checkout_rejects_concurrent_duplicate(client):
    headers = _register_and_login(client)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    headers["Idempotency-Key"] = "in-flight-key"

    IdempotencyRepository().reserve("in-flight-key", "checkout", user_id)  # left pending
    r = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
    assert r.status_code == 409


def test_checkout_rejects_key_reused_by_different_user(client):
    headers_a = _register_and_login(client, email="a@example.com")
    user_a = client.get("/auth/me", headers=headers_a).json()["id"]
    IdempotencyRepository().reserve("shared-key", "checkout", user_a)

    headers_b = _register_and_login(client, email="b@example.com")
    headers_b["Idempotency-Key"] = "shared-key"
    r = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers_b)
    assert r.status_code == 409


def test_failed_checkout_releases_key_for_retry(client, monkeypatch):
    headers = _register_and_login(client)
    headers["Idempotency-Key"] = "retry-key"

    def _boom(*args, **kwargs):
        raise billing_module.BillingNotConfigured("nope")

    monkeypatch.setattr(billing_module, "create_checkout_session", _boom)
    r1 = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
    assert r1.status_code == 503

    monkeypatch.setattr(
        billing_module, "create_checkout_session",
        lambda *a, **k: "https://stripe.test/session/1",
    )
    r2 = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == {"checkout_url": "https://stripe.test/session/1"}
