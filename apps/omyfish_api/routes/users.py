from fastapi import APIRouter, Depends, HTTPException, status

from apps.omyfish_api.auth import require_admin
from apps.omyfish_api.db.engine import ensure_db
from apps.omyfish_api.repositories.user_repository import UserRepository
from shared.schemas.user import TokenData, UserRead

router = APIRouter(prefix="/users", tags=["users"])


def _get_repo() -> UserRepository:
    ensure_db()
    return UserRepository()


@router.get("", response_model=list[UserRead])
def list_users(
    limit: int = 100,
    _: TokenData = Depends(require_admin),
    repo: UserRepository = Depends(_get_repo),
):
    return repo.list(limit)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    current: TokenData = Depends(require_admin),
    repo: UserRepository = Depends(_get_repo),
):
    if user_id == current.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    if not repo.delete(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
