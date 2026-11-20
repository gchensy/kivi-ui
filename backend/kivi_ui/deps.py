"""Request dependencies: database session, current user, role checks."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import ApiError
from .models import Role, User, UserStatus
from .security import read_session_token

Db = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Db) -> User:
    token = request.cookies.get(get_settings().cookie_name)
    claims = read_session_token(token) if token else None
    user = db.get(User, claims[0]) if claims else None
    if user is None or user.status is not UserStatus.active or user.token_version != claims[1]:
        raise ApiError(401, "unauthenticated", "Sign in to continue")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role is not Role.admin:
        raise ApiError(403, "forbidden", "Administrator role required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
