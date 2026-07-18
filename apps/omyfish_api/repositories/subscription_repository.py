from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from apps.omyfish_api.db.engine import new_id, get_db
from shared.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SubscriptionRepository:

    def start_trial(self, user_id: str) -> dict:
        """Idempotent: returns the existing row if the user already has one."""
        existing = self.get_for_user(user_id)
        if existing:
            return existing
        trial_end = _utcnow() + timedelta(days=settings.trial_days)
        with get_db() as db:
            db.execute(
                text(
                    "INSERT INTO subscriptions (id, user_id, status, trial_end) "
                    "VALUES (:id, :uid, 'trialing', :te)"
                ),
                {"id": new_id(), "uid": user_id, "te": trial_end.isoformat()},
            )
        return self.get_for_user(user_id)

    def get_for_user(self, user_id: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text("SELECT * FROM subscriptions WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()
        return self._effective(dict(row._mapping)) if row else None

    def set_active(self, user_id: str, plan: str, period_end: datetime | None,
                   stripe_customer_id: str | None = None,
                   stripe_subscription_id: str | None = None) -> None:
        self.start_trial(user_id)  # ensure a row exists
        with get_db() as db:
            db.execute(
                text("""
                    UPDATE subscriptions SET
                        status = 'active', plan = :plan,
                        current_period_end = :pe,
                        stripe_customer_id = COALESCE(:cust, stripe_customer_id),
                        stripe_subscription_id = COALESCE(:sub, stripe_subscription_id),
                        updated_at = :now
                    WHERE user_id = :uid
                """),
                {
                    "plan": plan,
                    "pe": period_end.isoformat() if period_end else None,
                    "cust": stripe_customer_id, "sub": stripe_subscription_id,
                    "now": _utcnow().isoformat(), "uid": user_id,
                },
            )

    def set_status(self, user_id: str, status: str) -> bool:
        with get_db() as db:
            result = db.execute(
                text(
                    "UPDATE subscriptions SET status = :s, updated_at = :now "
                    "WHERE user_id = :uid"
                ),
                {"s": status, "now": _utcnow().isoformat(), "uid": user_id},
            )
        return result.rowcount > 0

    def find_user_by_stripe_customer(self, customer_id: str) -> str | None:
        with get_db() as db:
            row = db.execute(
                text("SELECT user_id FROM subscriptions WHERE stripe_customer_id = :c"),
                {"c": customer_id},
            ).fetchone()
        return row[0] if row else None

    def list_all(self, limit: int = 500) -> list[dict]:
        with get_db() as db:
            rows = db.execute(
                text(
                    "SELECT s.*, u.email FROM subscriptions s "
                    "JOIN users u ON u.id = s.user_id "
                    "ORDER BY s.created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).fetchall()
        return [self._effective(dict(r._mapping)) for r in rows]

    def stats(self) -> dict:
        counts = {"trialing": 0, "active": 0, "canceled": 0, "expired": 0}
        plans = {"monthly": 0, "yearly": 0}
        for sub in self.list_all(limit=100_000):
            counts[sub["status"]] = counts.get(sub["status"], 0) + 1
            if sub["status"] == "active" and sub.get("plan") in plans:
                plans[sub["plan"]] += 1
        # 5 CAD/month, 29 CAD/year
        mrr_cad = plans["monthly"] * 5 + plans["yearly"] * 29 / 12
        return {"subscriptions": counts, "active_plans": plans, "mrr_cad": round(mrr_cad, 2)}

    @staticmethod
    def _effective(sub: dict) -> dict:
        """A trial past its end date reads as expired without a write."""
        sub["trial_end"] = _parse_dt(sub.get("trial_end"))
        sub["current_period_end"] = _parse_dt(sub.get("current_period_end"))
        if (
            sub["status"] == "trialing"
            and sub["trial_end"] is not None
            and sub["trial_end"] < _utcnow()
        ):
            sub["status"] = "expired"
        return sub
