"""Shop tab — Omyshop product catalog, cart, checkout, and order history.
Talks to the same shop.py / repositories as the FastAPI backend (in-process),
same pattern as admin.py's subscription_sidebar."""
import uuid

import streamlit as st


def _owner_kwargs(user: dict | None) -> dict:
    if user:
        return {"user_id": user["id"]}
    return {"guest_token": st.session_state["guest_cart_token"]}


def _cents_to_label(cents: int) -> str:
    return f"${cents / 100:.2f} CAD"


def render_shop_tab(user: dict | None) -> None:
    from apps.omyfish_api.db.engine import ensure_db
    from apps.omyfish_api import shop
    ensure_db()

    cart_count = sum(
        item["quantity"] for item in shop.get_cart_with_items(**_owner_kwargs(user))["items"]
    )
    _render_cart_badge(cart_count)

    if st.session_state.pop("_scroll_to_cart", False):
        _scroll_to_cart()

    st.subheader("Catalog")
    _render_catalog(user)

    st.divider()
    st.markdown('<div id="cart-anchor"></div>', unsafe_allow_html=True)
    st.subheader("Your cart")
    _render_cart(user)

    if user:
        st.divider()
        st.subheader("Your orders")
        _render_my_orders(user)
        if user.get("role") == "admin":
            st.divider()
            st.subheader("Admin — all orders")
            _render_admin_orders()
    else:
        st.divider()
        st.subheader("Track a guest order")
        _render_guest_order_lookup()


def _render_cart_badge(count: int) -> None:
    """Fixed top-right pill, offset from Streamlit's own top-right toolbar
    (hamburger/deploy buttons) rather than overlapping it. Pure CSS/HTML —
    no JS, so it degrades harmlessly (just an inert span) if a future
    Streamlit version changes something it relies on."""
    if count < 1:
        return
    st.markdown(f"""
        <style>
        .omyfish-cart-badge {{
            position: fixed; top: 0.6rem; right: 4.5rem; z-index: 999999;
            background: #2c5282; color: white; padding: 0.3rem 0.75rem;
            border-radius: 999px; font-size: 0.85rem; font-weight: 600;
            text-decoration: none; box-shadow: 0 1px 4px rgba(0,0,0,0.3);
        }}
        .omyfish-cart-badge:hover {{ background: #3a6ba5; }}
        </style>
        <a class="omyfish-cart-badge" href="#cart-anchor">🛒 Cart ({count})</a>
    """, unsafe_allow_html=True)


def _scroll_to_cart() -> None:
    """st.markdown(unsafe_allow_html=True) never runs <script> tags — the
    browser ignores script elements inserted via innerHTML. components.html
    renders in an actual iframe, where script execution works; the iframe
    is same-origin (served by the same Streamlit server), so window.parent
    can reach the real page's DOM to scroll it."""
    import streamlit.components.v1 as components
    components.html("""
        <script>
        var el = window.parent.document.getElementById('cart-anchor');
        if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
        </script>
    """, height=0)


def _render_catalog(user: dict | None) -> None:
    from apps.omyfish_api.repositories.product_repository import ProductRepository
    from apps.omyfish_api import shop

    products = ProductRepository().list_active()
    cols = st.columns(3)
    for i, product in enumerate(products):
        with cols[i % 3]:
            st.image(product["image_url"], use_container_width=True)
            if product.get("image_credit"):
                st.caption(product["image_credit"])
            st.markdown(f"**{product['name']}**")
            st.caption(product["description"])
            st.write(_cents_to_label(product["price_cents"]))
            st.caption(f"{product['stock_quantity']} in stock")
            if st.button("Add to cart", key=f"add_{product['id']}", use_container_width=True,
                         disabled=product["stock_quantity"] < 1):
                shop.add_to_cart(product["id"], 1, **_owner_kwargs(user))
                st.toast(f"Added {product['name']} to cart", icon="🛒")
                st.session_state["_scroll_to_cart"] = True
                st.rerun()


def _render_cart(user: dict | None) -> None:
    from apps.omyfish_api import shop

    # Rendered before the empty-cart check: checkout() clears the cart as
    # soon as it's called, so without this the link would vanish on the
    # very next rerun (any widget interaction anywhere on the page) with no
    # way to get back to it — leaving a pending_payment order with no way
    # to pay, same failure the Shop tab was reported stuck in.
    _render_pending_checkout_link()

    cart = shop.get_cart_with_items(**_owner_kwargs(user))
    if not cart["items"]:
        st.caption("Your cart is empty.")
        return

    total_cents = 0
    for item in cart["items"]:
        product = item["product"]
        total_cents += product["price_cents"] * item["quantity"]
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(f"{product['name']} — {_cents_to_label(product['price_cents'])} each")
        new_qty = c2.number_input("Qty", min_value=0, value=item["quantity"], step=1,
                                   key=f"qty_{product['id']}", label_visibility="collapsed")
        if new_qty != item["quantity"]:
            shop.update_cart_item(product["id"], int(new_qty), **_owner_kwargs(user))
            st.rerun()
        if c3.button("Remove", key=f"rm_{product['id']}"):
            shop.update_cart_item(product["id"], 0, **_owner_kwargs(user))
            st.rerun()

    st.write(f"**Total: {_cents_to_label(total_cents)}**")
    _render_checkout_button(user)


def _render_checkout_button(user: dict | None) -> None:
    from apps.omyfish_api import shop
    from apps.omyfish_api.billing import BillingNotConfigured
    from apps.omyfish_api.repositories.idempotency_repository import IdempotencyConflict, IdempotencyRepository
    from shared.config import settings

    guest_email = None
    if not user:
        guest_email = st.text_input("Email (for order confirmation + guest tracking)",
                                     key="shop_guest_email")

    if st.button("Checkout", use_container_width=True, type="primary"):
        if not user and not guest_email:
            st.error("Email is required to check out as a guest.")
            return
        idem_key = st.session_state.setdefault("shop_checkout_idem", str(uuid.uuid4()))
        idem_repo = IdempotencyRepository()
        owner_key = (user or {}).get("id") or st.session_state["guest_cart_token"]
        try:
            replay = idem_repo.reserve(idem_key, "shop_checkout", owner_key)
            if replay is not None:
                url = replay["checkout_url"]
            else:
                url = shop.checkout(
                    success_url=f"{settings.app_base_url}?shop=success&session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{settings.app_base_url}?shop=canceled",
                    idempotency_key=idem_key,
                    guest_email=guest_email,
                    **_owner_kwargs(user),
                )["checkout_url"]
                idem_repo.complete(idem_key, "shop_checkout", {"checkout_url": url})
            st.session_state.pop("shop_checkout_idem", None)
            st.session_state["shop_checkout_url"] = url
            st.rerun()  # _render_pending_checkout_link() runs before this
                        # button does, so without a rerun the link set above
                        # wouldn't show until some unrelated later rerun
        except BillingNotConfigured:
            idem_repo.release(idem_key, "shop_checkout")
            st.session_state.pop("shop_checkout_idem", None)
            st.session_state["shop_checkout_url"] = None
            st.rerun()
        except IdempotencyConflict:
            pass
        except Exception as e:
            idem_repo.release(idem_key, "shop_checkout")
            st.session_state.pop("shop_checkout_idem", None)
            st.error(f"Could not start checkout: {e}")


def _render_pending_checkout_link() -> None:
    """Kept in session_state (not popped on render) so it survives any
    rerun until the user actually proceeds to Stripe or a new checkout
    overwrites it — a link_button's click is a plain browser navigation,
    not a Streamlit rerun, so popping on render (not on click) was the bug:
    it vanished on the very next unrelated widget interaction."""
    if "shop_checkout_url" not in st.session_state:
        return
    url = st.session_state["shop_checkout_url"]
    if url:
        st.link_button("Continue to secure checkout →", url, use_container_width=True)
    else:
        st.session_state.pop("shop_checkout_url")
        st.caption("Payments are not configured on this deployment.")


def handle_shop_success_redirect() -> None:
    """Synchronous fallback mirroring admin.py's subscription confirm —
    covers the instant checkout completes while the real webhook may still
    be asleep from Render free-tier cold start."""
    from apps.omyfish_api import shop

    if st.query_params.get("shop") == "success" and st.query_params.get("session_id"):
        try:
            shop.confirm_shop_checkout_session(st.query_params["session_id"])
            st.success("Order confirmed — thank you!")
        except Exception:
            st.warning("Payment received, but we couldn't confirm it automatically — "
                       "contact support if your order doesn't show up shortly.")
        st.session_state.pop("shop_checkout_url", None)
        st.query_params.clear()
    elif st.query_params.get("shop") == "canceled":
        st.session_state.pop("shop_checkout_url", None)
        st.query_params.clear()


def _render_my_orders(user: dict) -> None:
    from apps.omyfish_api.repositories.order_repository import OrderRepository, RETURN_WINDOW_DAYS
    from apps.omyfish_api import shop
    from datetime import datetime, timedelta, timezone

    orders = OrderRepository().list_for_user(user["id"])
    if not orders:
        st.caption("No orders yet.")
        return
    for order in orders:
        with st.expander(f"Order {order['id'][:8]} — {order['status']} — "
                          f"{_cents_to_label(order['total_cents'])}"):
            for line in order["lines"]:
                st.write(f"{line['quantity']} × {line['product_name']} — "
                         f"{_cents_to_label(line['unit_price_cents'])} each")
            if order["status"] == "paid":
                within_window = (
                    order["paid_at"] is not None
                    and datetime.now(timezone.utc) <= order["paid_at"] + timedelta(days=RETURN_WINDOW_DAYS)
                )
                if within_window:
                    reason = st.text_input("Return reason", key=f"return_reason_{order['id']}")
                    if st.button("Request return", key=f"return_{order['id']}"):
                        try:
                            shop.request_return(order["id"], user["id"], reason)
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))


def _render_guest_order_lookup() -> None:
    from apps.omyfish_api.repositories.order_repository import OrderRepository

    order_id = st.text_input("Order ID", key="guest_lookup_id")
    email = st.text_input("Email used at checkout", key="guest_lookup_email")
    if st.button("Find order"):
        order = OrderRepository().get(order_id) if order_id else None
        if not order or order.get("guest_email") != email:
            st.error("No matching order found.")
        else:
            st.write(f"Status: **{order['status']}** — {_cents_to_label(order['total_cents'])}")
            for line in order["lines"]:
                st.write(f"{line['quantity']} × {line['product_name']}")


def _render_admin_orders() -> None:
    from apps.omyfish_api.repositories.order_repository import OrderRepository
    from apps.omyfish_api import shop

    orders = OrderRepository().list_all()
    for order in orders:
        label = f"{order['id'][:8]} — {order.get('user_id') or order.get('guest_email')} — {order['status']}"
        with st.expander(label):
            if order["status"] == "return_requested":
                if st.button("Approve return (refund)", key=f"approve_{order['id']}"):
                    try:
                        shop.approve_return(order["id"], idempotency_key=str(uuid.uuid4()))
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
