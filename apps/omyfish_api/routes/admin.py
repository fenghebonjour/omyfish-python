from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from apps.omyfish_api.auth import require_admin
from apps.omyfish_api.db.engine import ensure_db, get_db
from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository
from apps.omyfish_api.repositories.user_repository import UserRepository
from shared.schemas.user import TokenData

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _subs() -> SubscriptionRepository:
    ensure_db()
    return SubscriptionRepository()


@router.get("/stats")
def stats(repo: SubscriptionRepository = Depends(_subs)):
    with get_db() as db:
        user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        obs_count = db.execute(text("SELECT COUNT(*) FROM observations")).scalar()
    return {"users": user_count, "observations": obs_count, **repo.stats()}


@router.get("/subscriptions")
def subscriptions(repo: SubscriptionRepository = Depends(_subs)):
    subs = repo.list_all()
    for s in subs:
        s["trial_end"] = s["trial_end"].isoformat() if s.get("trial_end") else None
        s["current_period_end"] = (
            s["current_period_end"].isoformat() if s.get("current_period_end") else None
        )
    return subs


@router.post("/subscriptions/{user_id}/grant")
def grant(user_id: str, body: dict | None = None,
          repo: SubscriptionRepository = Depends(_subs)):
    """Comp a subscription: active for `days` (default 365), no Stripe involved."""
    if not UserRepository().get_by_id(user_id):
        raise HTTPException(404, "User not found")
    days = int((body or {}).get("days", 365))
    plan = (body or {}).get("plan", "yearly")
    repo.set_active(user_id, plan=plan,
                    period_end=datetime.now(timezone.utc) + timedelta(days=days))
    return repo_state(user_id, repo)


@router.post("/subscriptions/{user_id}/revoke")
def revoke(user_id: str, repo: SubscriptionRepository = Depends(_subs)):
    if not repo.set_status(user_id, "canceled"):
        raise HTTPException(404, "No subscription for that user")
    return repo_state(user_id, repo)


@router.post("/users/{user_id}/extend-trial")
def extend_trial(user_id: str, body: dict | None = None,
                 repo: SubscriptionRepository = Depends(_subs)):
    days = int((body or {}).get("days", 7))
    sub = repo.get_for_user(user_id) or repo.start_trial(user_id)
    new_end = max(
        sub["trial_end"] or datetime.now(timezone.utc), datetime.now(timezone.utc)
    ) + timedelta(days=days)
    with get_db() as db:
        db.execute(
            text(
                "UPDATE subscriptions SET status = 'trialing', trial_end = :te, "
                "updated_at = :now WHERE user_id = :uid"
            ),
            {"te": new_end.isoformat(), "now": datetime.now(timezone.utc).isoformat(),
             "uid": user_id},
        )
    return repo_state(user_id, repo)


def repo_state(user_id: str, repo: SubscriptionRepository) -> dict:
    sub = repo.get_for_user(user_id)
    return {
        "user_id": user_id,
        "status": sub["status"],
        "plan": sub.get("plan"),
        "trial_end": sub["trial_end"].isoformat() if sub.get("trial_end") else None,
        "current_period_end": sub["current_period_end"].isoformat()
        if sub.get("current_period_end") else None,
    }
