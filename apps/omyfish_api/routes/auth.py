from fastapi import APIRouter, Depends, HTTPException, status

from apps.omyfish_api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from apps.omyfish_api.db.engine import ensure_db
from apps.omyfish_api.repositories.user_repository import UserRepository
from shared.schemas.user import Token, TokenData, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_repo() -> UserRepository:
    ensure_db()
    return UserRepository()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, repo: UserRepository = Depends(_get_repo)):
    if repo.get_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return repo.create(body.email, hash_password(body.password))


@router.post("/login", response_model=Token)
def login(body: UserCreate, repo: UserRepository = Depends(_get_repo)):
    user = repo.get_by_email(body.email)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return Token(access_token=create_access_token(user["id"], user["role"]))


@router.get("/me", response_model=UserRead)
def me(
    token: TokenData = Depends(get_current_user),
    repo: UserRepository = Depends(_get_repo),
):
    user = repo.get_by_id(token.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
