import pytest
from fastapi import HTTPException

from apps.omyfish_api.auth import (
    _decode,
    create_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_token_roundtrip_carries_user_and_role():
    token = create_access_token("user-123", "admin")
    data = _decode(token)
    assert data.user_id == "user-123"
    assert data.role == "admin"


def test_tampered_token_rejected():
    token = create_access_token("user-123", "user")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(HTTPException) as exc:
        _decode(tampered)
    assert exc.value.status_code == 401
