"""SQLAlchemy ORM models for the platform metadata schema."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Enum, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Role(enum.StrEnum):
    admin = "admin"
    analyst = "analyst"


class UserStatus(enum.StrEnum):
    pending = "pending"
    active = "active"
    disabled = "disabled"


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda members: [m.value for m in members])


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.analyst)
    status: Mapped[UserStatus] = mapped_column(_enum(UserStatus, "user_status"), default=UserStatus.pending)
    locale: Mapped[str] = mapped_column(String(8), default="zh-CN")
    token_version: Mapped[int] = mapped_column(default=0)
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    actor: Mapped[User | None] = relationship(lazy="joined")


class AnalyticsSnapshot(Base):
    """Precomputed analysis payloads, keyed by name (for example ``demo``)."""

    __tablename__ = "analytics_snapshots"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
