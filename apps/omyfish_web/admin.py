"""Admin dashboard tab + sidebar subscription card for the Streamlit app.
Talks to the same repositories as the FastAPI backend (in-process)."""
from datetime import datetime, timedelta, timezone

import streamlit as st


def _subs_repo():
    from apps.omyfish_api.db.engine import ensure_db
    from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository
    ensure_db()
    return SubscriptionRepository()


# ── Sidebar subscription card (any logged-in user) ────────────────────────────

def subscription_sidebar(user: dict) -> None:
    from apps.omyfish_api import billing
    from apps.omyfish_api.billing import BillingNotConfigured

    repo = _subs_repo()
    sub = repo.get_for_user(user["id"]) or repo.start_trial(user["id"])
    status = sub["status"]

    if status == "trialing":
        days_left = max(0, (sub["trial_end"] - datetime.now(timezone.utc)).days)
        st.info(f"Free trial — {days_left} day{'s' if days_left != 1 else ''} left")
    elif status == "active":
        st.success(f"Subscribed — {billing.PLANS[sub['plan']]['label']}"
                   if sub.get("plan") in billing.PLANS else "Subscribed")
    else:
        st.warning("Trial ended — subscribe to keep full access")

    if status != "active":
        col1, col2 = st.columns(2)
        for col, plan in ((col1, "monthly"), (col2, "yearly")):
            with col:
                if st.button(billing.PLANS[plan]["label"], key=f"sub_{plan}",
                             use_container_width=True):
                    try:
                        url = billing.create_checkout_session(
                            user["id"], user["email"], plan)
                        st.session_state["checkout_url"] = url
                    except BillingNotConfigured:
                        st.session_state["checkout_url"] = None
        if "checkout_url" in st.session_state:
            if st.session_state["checkout_url"]:
                st.link_button("Continue to secure checkout →",
                               st.session_state.pop("checkout_url"),
                               use_container_width=True)
            else:
                st.session_state.pop("checkout_url")
                st.caption("Payments are not configured on this deployment.")


# ── Admin tab ─────────────────────────────────────────────────────────────────

def render_admin() -> None:
    from apps.omyfish_api.db.engine import get_db
    from sqlalchemy import text

    repo = _subs_repo()

    with get_db() as db:
        user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        obs_count = db.execute(text("SELECT COUNT(*) FROM observations")).scalar()
    stats = repo.stats()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Users", user_count)
    c2.metric("Observations", obs_count)
    c3.metric("Active subs", stats["subscriptions"].get("active", 0))
    c4.metric("On trial", stats["subscriptions"].get("trialing", 0))
    c5.metric("MRR (CAD)", f"${stats['mrr_cad']:.2f}")

    st.divider()
    st.subheader("Subscriptions")
    subs = repo.list_all()
    if subs:
        st.dataframe(
            [{
                "Email": s["email"],
                "Status": s["status"],
                "Plan": s.get("plan") or "—",
                "Trial ends": s["trial_end"].strftime("%Y-%m-%d")
                if s.get("trial_end") else "—",
                "Period ends": s["current_period_end"].strftime("%Y-%m-%d")
                if s.get("current_period_end") else "—",
            } for s in subs],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No subscriptions yet.")

    st.divider()
    st.subheader("Manage")
    if not subs:
        return
    emails = {s["email"]: s["user_id"] for s in subs}
    target_email = st.selectbox("User", sorted(emails))
    target = emails[target_email]
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("Grant 1 year (comp)", use_container_width=True):
            repo.set_active(target, plan="yearly",
                            period_end=datetime.now(timezone.utc) + timedelta(days=365))
            st.rerun()
    with a2:
        if st.button("Extend trial 7 days", use_container_width=True):
            sub = repo.get_for_user(target)
            base = max(sub["trial_end"] or datetime.now(timezone.utc),
                       datetime.now(timezone.utc))
            from apps.omyfish_api.db.engine import get_db as _gdb
            with _gdb() as db:
                db.execute(
                    text("UPDATE subscriptions SET status='trialing', trial_end=:te "
                         "WHERE user_id=:uid"),
                    {"te": (base + timedelta(days=7)).isoformat(), "uid": target},
                )
            st.rerun()
    with a3:
        if st.button("Revoke", use_container_width=True, type="secondary"):
            repo.set_status(target, "canceled")
            st.rerun()
