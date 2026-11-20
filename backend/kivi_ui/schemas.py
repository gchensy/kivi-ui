"""Pydantic request and response models."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from .models import Role, UserStatus

Locale = Literal["zh-CN", "en-US"]
_USERNAME = re.compile(r"^[a-z][a-z0-9_.-]{2,31}$")


def _password(value: str) -> str:
    if not (8 <= len(value) <= 128):
        raise ValueError("password must be 8 to 128 characters")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("password must contain letters and digits")
    return value


def _username(value: str) -> str:
    value = value.strip().lower()
    if not _USERNAME.match(value):
        raise ValueError(
            "username must be 3-32 characters: letters, digits, '_', '.', '-', starting with a letter"
        )
    return value


Username = Annotated[str, AfterValidator(_username)]
Password = Annotated[str, AfterValidator(_password)]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254, description="Username or email")
    password: str = Field(min_length=1, max_length=128)


class SignupIn(BaseModel):
    username: Username
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=64)
    password: Password
    locale: Locale = "zh-CN"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    display_name: str
    role: Role
    status: UserStatus
    locale: str
    last_login_at: datetime | None
    created_at: datetime


class SignupOut(BaseModel):
    user: UserOut
    requires_approval: bool


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=64)
    email: EmailStr | None = None
    locale: Locale | None = None


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class UserCreateIn(SignupIn):
    role: Role = Role.analyst


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=64)
    role: Role | None = None
    status: UserStatus | None = None


class PasswordResetIn(BaseModel):
    new_password: Password


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    counts: dict[UserStatus, int]


class AuditActor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: AuditActor | None
    action: str
    entity_type: str | None
    entity_id: str | None
    detail: dict[str, Any]
    ip: str | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditLogOut]
    total: int


class AuthConfigOut(BaseModel):
    signup_mode: Literal["approval", "open", "closed"]


class ErrorOut(BaseModel):
    code: str
    message: str
    detail: Any = None
