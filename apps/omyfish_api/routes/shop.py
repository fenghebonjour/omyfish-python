from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from apps.omyfish_api import shop
from apps.omyfish_api.auth import get_current_user, get_optional_user
from apps.omyfish_api.billing import BillingNotConfigured
from apps.omyfish_api.db.engine import ensure_db
from apps.omyfish_api.rate_limit import limit_by_ip
from apps.omyfish_api.repositories.idempotency_repository import IdempotencyConflict, IdempotencyRepository
from apps.omyfish_api.repositories.order_repository import InvalidOrderState
from apps.omyfish_api.repositories.product_repository import ProductRepository
from apps.omyfish_api.shop import CartEmptyException, InsufficientStockException
from shared.schemas.user import TokenData

router = APIRouter(prefix="/shop", tags=["shop"])


def _ensure():
    ensure_db()


def _resolve_owner(
    token: TokenData | None = Depends(get_optional_user),
    x_cart_token: str | None = Header(None),
) -> dict:
    """Exactly one of a valid JWT or X-Cart-Token identifies the cart owner —
    same pattern as omyfish-java's CartOwnerResolver."""
    has_user = token is not None and token.user_id is not None
    has_guest = bool(x_cart_token)
    if has_user == has_guest:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Exactly one of a bearer token or X-Cart-Token header is required",
        )
    if has_user:
        return {"user_id": token.user_id, "guest_token": None}
    return {"user_id": None, "guest_token": x_cart_token}


def _order_response(order: dict) -> dict:
    for field in ("created_at", "paid_at", "return_requested_at", "returned_at"):
        if order.get(field):
            order[field] = order[field].isoformat()
    return order


@router.get("/products")
def list_products():
    _ensure()
    return ProductRepository().list_active()


@router.get("/products/{product_id}")
def get_product(product_id: str):
    _ensure()
    product = ProductRepository().get(product_id)
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("/cart")
def get_cart(owner: dict = Depends(_resolve_owner)):
    _ensure()
    return shop.get_cart_with_items(**owner)


@router.post("/cart/items")
def add_cart_item(body: dict, owner: dict = Depends(_resolve_owner)):
    _ensure()
    product_id = body.get("product_id")
    quantity = int(body.get("quantity", 1))
    if not product_id or quantity < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "product_id and a positive quantity are required")
    return shop.add_to_cart(product_id, quantity, **owner)


@router.put("/cart/items/{product_id}")
def update_cart_item(product_id: str, body: dict, owner: dict = Depends(_resolve_owner)):
    _ensure()
    quantity = int(body.get("quantity", 0))
    return shop.update_cart_item(product_id, quantity, **owner)


@router.post("/cart/merge")
def merge_cart(body: dict, token: TokenData = Depends(get_current_user)):
    _ensure()
    guest_token = body.get("guest_token")
    if not guest_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "guest_token is required")
    return shop.merge_guest_cart(token.user_id, guest_token)


@router.post("/checkout", dependencies=[Depends(limit_by_ip)])
def checkout(
    body: dict,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    owner: dict = Depends(_resolve_owner),
):
    _ensure()
    guest_email = body.get("guest_email")
    if owner["user_id"] is None and not guest_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "guest_email is required for guest checkout")

    idem_repo = IdempotencyRepository()
    try:
        replay = idem_repo.reserve(idempotency_key, "shop_checkout", owner["user_id"] or owner["guest_token"])
    except IdempotencyConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    if replay is not None:
        return replay

    try:
        result = shop.checkout(
            success_url=body.get("success_url"),
            cancel_url=body.get("cancel_url"),
            idempotency_key=idempotency_key,
            guest_email=guest_email,
            **owner,
        )
    except BillingNotConfigured as e:
        idem_repo.release(idempotency_key, "shop_checkout")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except (CartEmptyException, InsufficientStockException) as e:
        idem_repo.release(idempotency_key, "shop_checkout")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception:
        idem_repo.release(idempotency_key, "shop_checkout")
        raise

    idem_repo.complete(idempotency_key, "shop_checkout", result)
    return result


@router.post("/webhook")
async def shop_webhook(request: Request):
    _ensure()
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = shop.verify_shop_webhook(payload, signature)
    except BillingNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")
    order_id = shop.apply_shop_event(event)
    return {"handled": order_id is not None}


@router.get("/orders/lookup")
def lookup_guest_order(order_id: str, email: str):
    _ensure()
    from apps.omyfish_api.repositories.order_repository import OrderRepository
    order = OrderRepository().get(order_id)
    if not order or order.get("guest_email") != email:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return _order_response(order)


@router.get("/orders")
def list_my_orders(token: TokenData = Depends(get_current_user)):
    _ensure()
    from apps.omyfish_api.repositories.order_repository import OrderRepository
    return [_order_response(o) for o in OrderRepository().list_for_user(token.user_id)]


@router.get("/orders/{order_id}")
def get_order(order_id: str, token: TokenData = Depends(get_current_user)):
    _ensure()
    from apps.omyfish_api.repositories.order_repository import OrderRepository
    order = OrderRepository().get(order_id)
    if not order or order.get("user_id") != token.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return _order_response(order)


@router.post("/orders/{order_id}/returns")
def request_return(order_id: str, body: dict, token: TokenData = Depends(get_current_user)):
    _ensure()
    reason = body.get("reason", "")
    try:
        shop.request_return(order_id, token.user_id, reason)
    except InvalidOrderState as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    from apps.omyfish_api.repositories.order_repository import OrderRepository
    return _order_response(OrderRepository().get(order_id))
