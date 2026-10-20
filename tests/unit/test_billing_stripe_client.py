import stripe

from apps.omyfish_api import billing
from shared.config import settings


def test_stripe_client_gets_connect_and_read_timeout(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(stripe, "default_http_client", None)

    billing._stripe()

    client = stripe.default_http_client
    assert isinstance(client, stripe.RequestsClient)
    assert client._timeout == (billing.CONNECT_TIMEOUT_S, billing.READ_TIMEOUT_S)


def test_stripe_client_is_not_recreated_once_set(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(stripe, "default_http_client", None)

    billing._stripe()
    first_client = stripe.default_http_client
    billing._stripe()
    assert stripe.default_http_client is first_client
