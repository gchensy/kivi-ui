"""Administrator account management."""

import uuid

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, or_, select

from .. import audit
from ..deps import AdminUser, Db
from ..errors import ApiError
from ..models import Role, User, UserStatus
from ..schemas import PasswordResetIn, UserCreateIn, UserOut, UserPage, UserUpdateIn
from ..security import hash_password
from .auth import ensure_unique

router = APIRouter(prefix="/users", tags=["users"])


def _get(db: Db, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "User not found")
    return user


@router.get("", response_model=UserPage)
def list_users(
    _: AdminUser,
    db: Db,
    q: str | None = Query(None, max_length=64),
    status_filter: UserStatus | None = Query(None, alias="status"),
    role: Role | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> UserPage:
    query = select(User)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                User.username.like(like),
                func.lower(User.email).like(like),
                func.lower(User.display_name).like(like),
            )
        )
    if role:
        query = query.where(User.role == role)
    matched = query.subquery()
    counts = {s: 0 for s in UserStatus}
    for value, count in db.execute(select(matched.c.status, func.count()).group_by(matched.c.status)).all():
        counts[UserStatus(value)] = count
    if status_filter:
        query = query.where(User.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by((User.status == UserStatus.pending).desc(), User.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return UserPage(items=[UserOut.model_validate(u) for u in items], total=total, counts=counts)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreateIn, request: Request, admin: AdminUser, db: Db) -> User:
    email = str(body.email).lower()
    ensure_unique(db, body.username, email)
    user = User(
        username=body.username,
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        role=body.role,
        status=UserStatus.active,
        locale=body.locale,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        "user.created",
        actor=admin,
        request=request,
        entity_type="user",
        entity_id=user.id,
        username=user.username,
        role=user.role.value,
    )
    db.commit()
    return user


def _active_admins(db: Db) -> int:
    return (
        db.scalar(select(func.count()).where(User.role == Role.admin, User.status == UserStatus.active)) or 0
    )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdateIn, request: Request, admin: AdminUser, db: Db) -> User:
    user = _get(db, user_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if user.id == admin.id and ({"role", "status"} & changes.keys()):
        raise ApiError(400, "cannot_change_self", "You cannot change your own role or status")
    losing_admin = (
        user.role is Role.admin
        and user.status is UserStatus.active
        and (
            changes.get("role", Role.admin) is not Role.admin
            or changes.get("status", UserStatus.active) is not UserStatus.active
        )
    )
    if losing_admin and _active_admins(db) <= 1:
        raise ApiError(400, "last_admin", "At least one active administrator is required")

    before = {k: getattr(user, k) for k in changes}
    for key, value in changes.items():
        setattr(user, key, value.strip() if isinstance(value, str) else value)
    if {"role", "status"} & changes.keys():
        user.token_version += 1  # end existing sessions with the old permissions
    if changes.get("status") is UserStatus.active:
        user.failed_logins, user.locked_until = 0, None
    audit.record(
        db,
        "user.updated",
        actor=admin,
        request=request,
        entity_type="user",
        entity_id=user.id,
        username=user.username,
        changes={k: [str(before[k]), str(getattr(user, k))] for k in changes},
    )
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: uuid.UUID, body: PasswordResetIn, request: Request, admin: AdminUser, db: Db
) -> User:
    user = _get(db, user_id)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    user.failed_logins, user.locked_until = 0, None
    audit.record(
        db,
        "user.password_reset",
        actor=admin,
        request=request,
        entity_type="user",
        entity_id=user.id,
        username=user.username,
    )
    db.commit()
    return user
