import re
from typing import Optional
from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    email: str
    password: str


class UserRegister(UserCreate):
    """Registration enforces credential rules; login (UserCreate) stays loose
    so existing accounts are never locked out by a rule change."""

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, v: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Invalid email address")
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserRead(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None
