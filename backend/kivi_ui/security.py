"""Password hashing and signed session tokens."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import get_settings
from .models import User

_hasher = PasswordHasher()
# Verified against when the username is unknown, so both paths cost one hash.
_DUMMY_HASH = _hasher.hash("kivi-ui-timing-equaliser")
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_session_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "ver": user.token_version,
        "iat": now,
        "exp": now + timedelta(hours=settings.session_hours),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM)


def read_session_token(token: str) -> tuple[uuid.UUID, int] | None:
    try:
        claims = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "ver", "exp"]},
        )
        return uuid.UUID(claims["sub"]), int(claims["ver"])
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
