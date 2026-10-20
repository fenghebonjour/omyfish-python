from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from apps.omyfish_api import billing
from apps.omyfish_api.auth import get_current_user
from apps.omyfish_api.billing import BillingNotConfigured
from apps.omyfish_api.db.engine import ensure_db
from apps.omyfish_api.rate_limit import limit_by_ip
from apps.omyfish_api.repositories.idempotency_repository import IdempotencyConflict, IdempotencyRepository
from apps.omyfish_api.repositories.subscription_repository import SubscriptionRepository
from apps.omyfish_api.repositories.user_repository import UserRepository
from shared.schemas.user import TokenData

router = APIRouter(prefix="/billing", tags=["billing"])


def _get_repo() -> SubscriptionRepository:
    ensure_db()
    return SubscriptionRepository()


@router.get("/plans")
def plans():
    return billing.PLANS


@router.get("/me")
def my_subscription(
    token: TokenData = Depends(get_current_user),
    repo: SubscriptionRepository = Depends(_get_repo),
):
    sub = repo.get_for_user(token.user_id) or repo.start_trial(token.user_id)
    return {
        "status": sub["status"],
        "plan": sub.get("plan"),
        "trial_end": sub["trial_end"].isoformat() if sub.get("trial_end") else None,
        "current_period_end": sub["current_period_end"].isoformat()
        if sub.get("current_period_end") else None,
    }


@router.post("/checkout", dependencies=[Depends(limit_by_ip)])
def checkout(
    body: dict,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    token: TokenData = Depends(get_current_user),
    repo: SubscriptionRepository = Depends(_get_repo),
):
    plan = body.get("plan")
    if plan not in billing.PLANS:
        raise HTTPException(400, f"plan must be one of {sorted(billing.PLANS)}")
    user = UserRepository().get_by_id(token.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    idem_repo = IdempotencyRepository()
    try:
        replay = idem_repo.reserve(idempotency_key, "checkout", token.user_id)
    except IdempotencyConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    if replay is not None:
        return replay

    try:
        url = billing.create_checkout_session(
            token.user_id, user["email"], plan, idempotency_key=idempotency_key
        )
    except BillingNotConfigured as e:
        idem_repo.release(idempotency_key, "checkout")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except Exception:
        idem_repo.release(idempotency_key, "checkout")
        raise

    result = {"checkout_url": url}
    idem_repo.complete(idempotency_key, "checkout", result)
    return result


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    repo: SubscriptionRepository = Depends(_get_repo),
):
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = billing.verify_webhook(payload, signature)
    except BillingNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")
    user_id = billing.apply_event(event, repo)
    return {"handled": user_id is not None}
