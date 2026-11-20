"""Sign-in, sign-up, sign-out and the current user's own profile."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import func, or_, select

from .. import audit
from ..config import get_settings
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..models import Role, User, UserStatus
from ..schemas import (
    AuthConfigOut,
    LoginIn,
    PasswordChangeIn,
    ProfileIn,
    SignupIn,
    SignupOut,
    UserOut,
)
from ..security import (
    create_session_token,
    hash_password,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        create_session_token(user),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def ensure_unique(db: Db, username: str | None, email: str | None, exclude: User | None = None):
    for field, value, code in (
        (User.username, username, "username_taken"),
        (User.email, email, "email_taken"),
    ):
        if value is None:
            continue
        query = select(User.id).where(func.lower(field) == value.lower())
        if exclude is not None:
            query = query.where(User.id != exclude.id)
        if db.scalar(query) is not None:
            raise ApiError(409, code, f"{field.key} is already registered")


@router.get("/config", response_model=AuthConfigOut)
def auth_config() -> AuthConfigOut:
    return AuthConfigOut(signup_mode=get_settings().signup_mode)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Db) -> User:
    settings = get_settings()
    name = body.username.strip().lower()
    user = db.scalar(select(User).where(or_(User.username == name, User.email == name)))
    now = datetime.now(UTC)

    if user is not None and user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise ApiError(423, "account_locked", "Too many failed attempts", {"minutes": minutes})

    if not verify_password(user.password_hash if user else None, body.password):
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
            audit.record(
                db, "auth.login_failed", actor=user, request=request, entity_type="user", entity_id=user.id
            )
            db.commit()
        raise ApiError(401, "invalid_credentials", "Incorrect username or password")

    if user.status is UserStatus.pending:
        raise ApiError(403, "account_pending", "This account is waiting for administrator approval")
    if user.status is UserStatus.disabled:
        raise ApiError(403, "account_disabled", "This account has been disabled")

    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    audit.record(db, "auth.login", actor=user, request=request, entity_type="user", entity_id=user.id)
    db.commit()
    set_session_cookie(response, user)
    return user


@router.post("/signup", response_model=SignupOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, request: Request, db: Db) -> SignupOut:
    mode = get_settings().signup_mode
    if mode == "closed":
        raise ApiError(403, "signup_closed", "Self-service sign-up is disabled")
    email = str(body.email).lower()
    ensure_unique(db, body.username, email)
    user = User(
        username=body.username,
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        role=Role.analyst,
        status=UserStatus.pending if mode == "approval" else UserStatus.active,
        locale=body.locale,
    )
    db.add(user)
    db.flush()
    audit.record(db, "auth.signup", actor=user, request=request, entity_type="user", entity_id=user.id)
    db.commit()
    return SignupOut(user=UserOut.model_validate(user), requires_approval=mode == "approval")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileIn, request: Request, user: CurrentUser, db: Db) -> User:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "email" in changes:
        changes["email"] = str(changes["email"]).lower()
        ensure_unique(db, None, changes["email"], exclude=user)
    if "display_name" in changes:
        changes["display_name"] = changes["display_name"].strip()
    for key, value in changes.items():
        setattr(user, key, value)
    audit.record(
        db,
        "user.profile_updated",
        actor=user,
        request=request,
        entity_type="user",
        entity_id=user.id,
        fields=sorted(changes),
    )
    db.commit()
    return user


@router.post("/password", response_model=UserOut)
def change_password(
    body: PasswordChangeIn, request: Request, response: Response, user: CurrentUser, db: Db
) -> User:
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(400, "wrong_password", "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit.record(
        db, "user.password_changed", actor=user, request=request, entity_type="user", entity_id=user.id
    )
    db.commit()
    set_session_cookie(response, user)
    return user
