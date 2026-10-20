"""Per-IP rate limiting on /billing/checkout."""
from shared.config import settings


def _register_and_login(client, email="sub@example.com"):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sixth_checkout_request_in_a_minute_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    headers = _register_and_login(client)

    for i in range(5):
        headers["Idempotency-Key"] = f"key-{i}"
        r = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
        assert r.status_code == 503  # stripe unconfigured, but not rate-limited yet

    headers["Idempotency-Key"] = "key-6"
    r = client.post("/billing/checkout", json={"plan": "monthly"}, headers=headers)
    assert r.status_code == 429


def test_webhook_path_is_never_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    for _ in range(50):
        r = client.post("/billing/webhook", content=b"{}",
                         headers={"stripe-signature": "x"})
        assert r.status_code != 429
