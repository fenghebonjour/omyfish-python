"""Admin reconciliation endpoint (Stripe calls stubbed)."""
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


def test_reconcile_requires_admin(client):
    headers = _register_and_login(client, "angler@example.com")
    assert client.post("/admin/subscriptions/reconcile", headers=headers).status_code == 403


def test_reconcile_repairs_missing_link_and_resyncs(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]

    monkeypatch.setattr(
        billing_module, "list_recent_subscriptions",
        lambda since: [{
            "user_id": target, "plan": "yearly",
            "stripe_customer_id": "cus_abc", "stripe_subscription_id": "sub_abc",
            "status": "active", "current_period_end": 4102444800,  # 2100-01-01
        }],
    )
    r = client.post("/admin/subscriptions/reconcile", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"repaired": 1, "resynced": 1, "skipped": 0}

    sub = SubscriptionRepository().get_for_user(target)
    assert sub["stripe_customer_id"] == "cus_abc"
    assert sub["stripe_subscription_id"] == "sub_abc"
    assert sub["status"] == "active" and sub["plan"] == "yearly"


def test_reconcile_already_linked_skips_repair_but_still_resyncs(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]
    repo = SubscriptionRepository()
    repo.set_active(target, plan="monthly", period_end=None,
                     stripe_customer_id="cus_abc", stripe_subscription_id="sub_abc")

    monkeypatch.setattr(
        billing_module, "list_recent_subscriptions",
        lambda since: [{
            "user_id": target, "plan": "monthly",
            "stripe_customer_id": "cus_abc", "stripe_subscription_id": "sub_abc",
            "status": "active", "current_period_end": 4102444800,
        }],
    )
    r = client.post("/admin/subscriptions/reconcile", headers=headers)
    assert r.json() == {"repaired": 0, "resynced": 1, "skipped": 0}


def test_reconcile_cancels_candidate_reported_canceled(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    target_headers = _register_and_login(client, "angler@example.com")
    target = client.get("/auth/me", headers=target_headers).json()["id"]

    monkeypatch.setattr(
        billing_module, "list_recent_subscriptions",
        lambda since: [{
            "user_id": target, "plan": "monthly",
            "stripe_customer_id": "cus_abc", "stripe_subscription_id": "sub_abc",
            "status": "canceled", "current_period_end": None,
        }],
    )
    client.post("/admin/subscriptions/reconcile", headers=headers)
    assert SubscriptionRepository().get_for_user(target)["status"] == "canceled"


def test_reconcile_one_bad_candidate_does_not_stop_others(client, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    good_headers = _register_and_login(client, "angler@example.com")
    good_user = client.get("/auth/me", headers=good_headers).json()["id"]

    monkeypatch.setattr(
        billing_module, "list_recent_subscriptions",
        lambda since: [
            {
                "user_id": "no-such-user-but-crashes-on-write", "plan": None,
                "stripe_customer_id": None, "stripe_subscription_id": None,
                "status": "active", "current_period_end": object(),  # bad type -> raises
            },
            {
                "user_id": good_user, "plan": "monthly",
                "stripe_customer_id": "cus_xyz", "stripe_subscription_id": "sub_xyz",
                "status": "active", "current_period_end": 4102444800,
            },
        ],
    )
    r = client.post("/admin/subscriptions/reconcile", headers=headers)
    assert r.json() == {"repaired": 1, "resynced": 1, "skipped": 1}
    assert SubscriptionRepository().get_for_user(good_user)["stripe_customer_id"] == "cus_xyz"
