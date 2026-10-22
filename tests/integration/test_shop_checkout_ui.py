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

_SCRIPT_LOGGED_IN = """
import streamlit as st
from apps.omyfish_api.db.engine import ensure_db
ensure_db()
from apps.omyfish_web.shop import render_shop_tab, handle_shop_success_redirect
handle_shop_success_redirect()
render_shop_tab({"id": "user-1", "role": "user"})
"""


def _setup_db_and_stripe(tmp_path, monkeypatch, session_counter=None):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(eng, "engine", test_engine)
    monkeypatch.setattr(eng, "Session", sessionmaker(bind=test_engine))
    monkeypatch.setattr(eng, "_db_initialized", False)

    def _create(**kw):
        if session_counter is not None:
            session_counter[0] += 1
            n = session_counter[0]
            return {"id": f"cs_test_{n}", "url": f"https://stripe.test/checkout/cs_test_{n}"}
        return {"id": "cs_test_abc", "url": "https://stripe.test/checkout/cs_test_abc"}

    fake_stripe = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(create=_create)))
    monkeypatch.setattr(billing_module, "_stripe", lambda: fake_stripe)

    from shared.config import settings
    monkeypatch.setattr(settings, "app_base_url", "https://omyfish.test")


@pytest.fixture
def shop_app(tmp_path, monkeypatch):
    _setup_db_and_stripe(tmp_path, monkeypatch)
    at = AppTest.from_string(_SCRIPT)
    at.run()
    return at


@pytest.fixture
def shop_app_logged_in(tmp_path, monkeypatch):
    counter = [0]
    _setup_db_and_stripe(tmp_path, monkeypatch, session_counter=counter)
    at = AppTest.from_string(_SCRIPT_LOGGED_IN)
    at.run()
    return at


def _checkout(at):
    at.button(key="add_shop-seed-0004").click().run()
    at.text_input(key="shop_guest_email").set_value("tester@example.com").run()
    [b for b in at.button if b.label == "Checkout"][0].click().run()


def _badge_markdown(at):
    return [m.value for m in at.get("markdown") if "omyfish-cart-badge" in m.value]


def test_cart_badge_shows_count_and_hides_when_empty(shop_app):
    at = shop_app
    assert _badge_markdown(at) == []  # empty cart: no badge at all

    at.button(key="add_shop-seed-0004").click().run()
    assert 'omyfish-cart-count">1<' in _badge_markdown(at)[0]

    at.button(key="add_shop-seed-0005").click().run()
    assert 'omyfish-cart-count">2<' in _badge_markdown(at)[0]

    _checkout(at)
    assert _badge_markdown(at) == []  # checkout cleared the cart


def test_add_to_cart_sets_scroll_flag_which_is_consumed_once(shop_app):
    at = shop_app
    at.button(key="add_shop-seed-0004").click().run()
    assert "_scroll_to_cart" not in at.session_state  # consumed by the same run
    at.run()
    assert not at.exception


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


def _checkout_logged_in(at, product_key="add_shop-seed-0004"):
    at.button(key=product_key).click().run()
    [b for b in at.button if b.label == "Checkout"][0].click().run()


def test_pending_order_gets_a_working_pay_now_button(shop_app_logged_in):
    from apps.omyfish_api.repositories.order_repository import OrderRepository

    at = shop_app_logged_in
    _checkout_logged_in(at)

    orders = OrderRepository().list_for_user("user-1")
    assert len(orders) == 1 and orders[0]["status"] == "pending_payment"
    order_id = orders[0]["id"]

    pay_buttons = [b for b in at.button if b.key == f"pay_{order_id}"]
    assert len(pay_buttons) == 1, "pending order should show a Pay now button"
    pay_buttons[0].click().run()

    assert not at.exception
    assert at.session_state[f"shop_resume_url_{order_id}"].startswith("https://stripe.test/")

    # Survives an unrelated rerun too, same persistence fix as the cart link.
    at.run()
    assert at.session_state[f"shop_resume_url_{order_id}"].startswith("https://stripe.test/")


def test_multiple_pending_orders_each_keep_their_own_resume_link(shop_app_logged_in):
    """Regression: a single shared session_state slot meant only the most
    recently generated resume link was ever reachable -- clicking "Pay now"
    on an older pending order would silently do nothing useful once a newer
    one existed. Each order now gets its own slot."""
    from apps.omyfish_api.repositories.order_repository import OrderRepository

    at = shop_app_logged_in
    _checkout_logged_in(at, product_key="add_shop-seed-0004")
    _checkout_logged_in(at, product_key="add_shop-seed-0005")

    orders = OrderRepository().list_for_user("user-1")
    assert len(orders) == 2
    order_a, order_b = orders[0]["id"], orders[1]["id"]

    [b for b in at.button if b.key == f"pay_{order_a}"][0].click().run()
    [b for b in at.button if b.key == f"pay_{order_b}"][0].click().run()

    url_a = at.session_state[f"shop_resume_url_{order_a}"]
    url_b = at.session_state[f"shop_resume_url_{order_b}"]
    assert url_a and url_b and url_a != url_b


def test_guest_order_lookup_pay_now_survives_its_own_rerun(shop_app):
    """The lookup result lived only in a local variable inside the "Find
    order" button's `if`, so clicking "Pay now" (its own button, its own
    rerun) would reset "Find order" to False and hide the very order
    details the Pay now button needs — the same session-state-across-
    reruns trap as the main checkout link bug."""
    from apps.omyfish_api.repositories.order_repository import OrderRepository

    at = shop_app
    _checkout(at)
    order = OrderRepository().list_all()[0]
    assert order["status"] == "pending_payment"

    at.text_input(key="guest_lookup_id").set_value(order["id"]).run()
    at.text_input(key="guest_lookup_email").set_value("tester@example.com").run()
    [b for b in at.button if b.label == "Find order"][0].click().run()

    assert not at.exception
    assert any("pending_payment" in m.value for m in at.get("markdown"))

    pay_buttons = [b for b in at.button if b.key == f"pay_{order['id']}"]
    assert len(pay_buttons) == 1
    pay_buttons[0].click().run()

    assert not at.exception
    # Order details must still be showing, not hidden by "Find order"
    # resetting to False on this rerun.
    assert any("pending_payment" in m.value for m in at.get("markdown"))
    assert at.session_state[f"shop_resume_url_{order['id']}"]


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
