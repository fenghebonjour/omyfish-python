"""Synchronous checkout-session confirmation fallback (BACKLOG.md item C,
step 1) — the interim activation path used while no webhook endpoint is
reachable on the deployment."""
from types import SimpleNamespace

import apps.omyfish_api.billing as billing_module
from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository


def _register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _stub_stripe(monkeypatch, session: dict):
    fake_stripe = SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(retrieve=lambda sid: session))
    )
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)


def test_confirm_checkout_session_activates_subscription(client, monkeypatch):
    headers = _register_and_login(client, "angler@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    repo = SubscriptionRepository()

    _stub_stripe(monkeypatch, {
        "status": "complete",
        "client_reference_id": user_id,
        "customer": "cus_test123",
        "subscription": "sub_test123",
        "metadata": {"user_id": user_id, "plan": "yearly"},
    })

    assert billing_module.confirm_checkout_session("cs_test_abc", repo) == user_id

    me = client.get("/billing/me", headers=headers).json()
    assert me["status"] == "active" and me["plan"] == "yearly"


def test_confirm_checkout_session_incomplete_is_ignored(client, monkeypatch):
    repo = SubscriptionRepository()
    _stub_stripe(monkeypatch, {"status": "open"})
    assert billing_module.confirm_checkout_session("cs_test_abc", repo) is None


def test_confirm_checkout_session_is_not_reapplied_for_same_session_id(client, monkeypatch):
    headers = _register_and_login(client, "angler2@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    repo = SubscriptionRepository()

    _stub_stripe(monkeypatch, {
        "status": "complete",
        "client_reference_id": user_id,
        "customer": "cus_test123",
        "subscription": "sub_test123",
        "metadata": {"user_id": user_id, "plan": "monthly"},
    })
    billing_module.confirm_checkout_session("cs_test_dup", repo)

    # A second call for the same session id (e.g. a Streamlit rerun of the
    # same page load) must not reapply activation — proven by swapping in a
    # stub that would activate a different plan and confirming it doesn't take.
    _stub_stripe(monkeypatch, {
        "status": "complete",
        "client_reference_id": user_id,
        "customer": "cus_test123",
        "subscription": "sub_test123",
        "metadata": {"user_id": user_id, "plan": "yearly"},
    })
    billing_module.confirm_checkout_session("cs_test_dup", repo)

    me = client.get("/billing/me", headers=headers).json()
    assert me["plan"] == "monthly"
