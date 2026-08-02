import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import InvalidTokenError, create_access_token, decode_access_token
from app.core.config import settings
from app.models.enums import UserRole


def test_passwords_are_hashed_and_verified() -> None:
    plaintext = "correct-horse-battery-staple"
    encoded = hash_password(plaintext)

    assert encoded != plaintext
    assert verify_password(plaintext, encoded)
    assert not verify_password("incorrect-password", encoded)
    assert not verify_password(plaintext, "not-a-password-hash")


def test_access_token_contains_validated_identity_claims() -> None:
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id, UserRole.ADMIN)

    claims = decode_access_token(token)

    assert claims.user_id == user_id
    assert claims.role is UserRole.ADMIN
    assert expires_in == settings.access_token_expire_minutes * 60


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"type": "refresh"},
        {"role": "NOT_A_ROLE"},
        {"jti": "not-a-uuid"},
    ],
)
def test_invalid_access_token_claims_are_rejected(overrides: dict[str, object]) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "role": UserRole.STUDENT.value,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(overrides)
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_signed_with_another_key_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": UserRole.STUDENT.value,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        "a-different-signing-key-with-enough-entropy",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
