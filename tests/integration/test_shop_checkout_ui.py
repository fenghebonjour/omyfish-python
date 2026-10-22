"""Streamlit Shop tab checkout UI: the "Continue to secure checkout" link
must survive reruns, not just the single pass that creates it. Regression
for a bug where the link was popped from session_state on render (not on
click — a link_button's click is a plain browser navigation, not a
Streamlit rerun) and the block that rendered it was gated behind the cart's
"is it empty" check, which checkout() itself flips true — so any further
rerun (e.g. clicking "Checkout" again, or any unrelated widget interaction)
permanently lost the link, leaving a pending_payment order with no way to
pay. An AppTest end-to-end run is required here: pytest's API-level tests
can't see a bug that only exists in Streamlit's session-state-across-reruns
behavior (see BACKLOG.md item D for the same lesson from the guest-cart-
token bug)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from streamlit.testing.v1 import AppTest

import apps.omyfish_api.billing as billing_module
import apps.omyfish_api.db.engine as eng

_SCRIPT = """
import streamlit as st
if "guest_cart_token" not in st.session_state:
    st.session_state["guest_cart_token"] = "guest-test-token"
from apps.omyfish_api.db.engine import ensure_db
ensure_db()
from apps.omyfish_web.shop import render_shop_tab, handle_shop_success_redirect
handle_shop_success_redirect()
render_shop_tab(None)
"""


@pytest.fixture
def shop_app(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(eng, "engine", test_engine)
    monkeypatch.setattr(eng, "Session", sessionmaker(bind=test_engine))
    monkeypatch.setattr(eng, "_db_initialized", False)

    fake_stripe = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(
        create=lambda **kw: {"id": "cs_test_abc", "url": "https://stripe.test/checkout/cs_test_abc"}
    )))
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)

    from shared.config import settings
    monkeypatch.setattr(settings, "app_base_url", "https://omyfish.test")

    at = AppTest.from_string(_SCRIPT)
    at.run()
    return at


def _checkout(at):
    at.button(key="add_shop-seed-0004").click().run()
    at.text_input(key="shop_guest_email").set_value("tester@example.com").run()
    [b for b in at.button if b.label == "Checkout"][0].click().run()


def test_checkout_link_survives_unrelated_rerun(shop_app):
    at = shop_app
    _checkout(at)

    assert not at.exception
    assert at.session_state["shop_checkout_url"] == "https://stripe.test/checkout/cs_test_abc"
    assert any("empty" in c.value.lower() for c in at.get("caption"))

    # Simulate the user doing anything else that triggers a rerun (e.g.
    # clicking "Checkout" again out of confusion) before following the link.
    at.run()
    at.run()

    assert not at.exception
    assert at.session_state["shop_checkout_url"] == "https://stripe.test/checkout/cs_test_abc"


def test_checkout_link_cleared_after_success_redirect(shop_app, monkeypatch):
    at = shop_app
    monkeypatch.setattr(
        "apps.omyfish_api.shop.confirm_shop_checkout_session", lambda session_id: "order-fake-1"
    )
    _checkout(at)
    assert at.session_state["shop_checkout_url"]

    at.query_params["shop"] = "success"
    at.query_params["session_id"] = "cs_test_abc"
    at.run()

    assert not at.exception
    assert "shop_checkout_url" not in at.session_state
    assert any("confirmed" in s.value.lower() for s in at.success)
