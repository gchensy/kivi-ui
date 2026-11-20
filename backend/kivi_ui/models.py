"""SQLAlchemy ORM models for the platform metadata schema."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Enum, ForeignKey, Identity, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
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


# ---- P2: datasets, indicators, binning schemes --------------------------------------------


class Dataset(Base):
    """An uploaded sample, stored as a physical table in the ``kivi_data`` schema."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(1000), default="")
    source: Mapped[str] = mapped_column(String(16), default="upload")  # upload | demo
    file_name: Mapped[str | None] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(63), unique=True)
    row_count: Mapped[int] = mapped_column(default=0)
    column_count: Mapped[int] = mapped_column(default=0)
    target_column: Mapped[str | None] = mapped_column(String(63))
    target_event: Mapped[str | None] = mapped_column(String(64))
    date_column: Mapped[str | None] = mapped_column(String(63))
    id_column: Mapped[str | None] = mapped_column(String(63))
    bad_rate: Mapped[float | None]
    profile: Mapped[dict[str, Any]] = mapped_column(default=dict)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")
    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetColumn.position"
    )


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    __table_args__ = (UniqueConstraint("dataset_id", "column_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    name: Mapped[str] = mapped_column(String(255))  # header as uploaded
    column_name: Mapped[str] = mapped_column(String(63))  # sanitized SQL name
    dtype: Mapped[str] = mapped_column(String(16))  # numeric | category | datetime | text
    role: Mapped[str] = mapped_column(String(16), default="feature")  # feature | target | id | date | ignore
    missing_rate: Mapped[float] = mapped_column(default=0.0)
    unique_count: Mapped[int] = mapped_column(default=0)
    iv: Mapped[float | None]
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="columns")


class Indicator(Base):
    __tablename__ = "indicators"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(16), default="other")
    description: Mapped[str] = mapped_column(String(2000), default="")
    kind: Mapped[str] = mapped_column(String(16))  # numeric | category
    unit: Mapped[str | None] = mapped_column(String(16))  # count | ratio | cny | years
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | published | retired
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    column_name: Mapped[str] = mapped_column(String(63))
    default_scheme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "binning_schemes.id", ondelete="SET NULL", use_alter=True, name="fk_indicator_default_scheme"
        )
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")
    dataset: Mapped[Dataset | None] = relationship(lazy="joined")
    default_scheme: Mapped["BinningScheme | None"] = relationship(
        foreign_keys=[default_scheme_id], lazy="joined", post_update=True
    )
    schemes: Mapped[list["BinningScheme"]] = relationship(
        foreign_keys="BinningScheme.indicator_id",
        back_populates="indicator",
        cascade="all, delete-orphan",
        order_by="BinningScheme.created_at.desc()",
    )


class BinningScheme(Base):
    """A saved binning of an indicator: the fitted rule plus its bin report."""

    __tablename__ = "binning_schemes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    indicator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("indicators.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(16))
    spec: Mapped[dict[str, Any]] = mapped_column(default=dict)
    rule: Mapped[dict[str, Any]] = mapped_column(default=dict)
    bins: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    iv: Mapped[float]
    trend: Mapped[str] = mapped_column(String(16))
    missing_rate: Mapped[float] = mapped_column(default=0.0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    indicator: Mapped[Indicator] = relationship(foreign_keys=[indicator_id], back_populates="schemes")
    author: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="joined")


# ---- P3: models, versions, reviews and background jobs -------------------------------------


class Job(Base):
    """A unit of background work (training, scoring) claimed by the worker."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), default="queued", index=True
    )  # queued|running|done|failed
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(String(2000))
    progress: Mapped[float] = mapped_column(default=0.0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class RiskModel(Base):
    __tablename__ = "risk_models"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128))
    scene: Mapped[str] = mapped_column(String(16), default="application")
    description: Mapped[str] = mapped_column(String(2000), default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")
    versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="ModelVersion.version.desc()"
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version"),
        Index("uq_model_online", "model_id", unique=True, postgresql_where=text("status = 'online'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_models.id", ondelete="CASCADE"), index=True)
    version: Mapped[int]
    # training | failed | draft | in_review | approved | online | retired
    status: Mapped[str] = mapped_column(String(16), default="training")
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    feature_count: Mapped[int] = mapped_column(default=0)
    auc_train: Mapped[float | None]
    auc_test: Mapped[float | None]
    auc_oot: Mapped[float | None]
    ks_train: Mapped[float | None]
    ks_test: Mapped[float | None]
    ks_oot: Mapped[float | None]
    notes: Mapped[str] = mapped_column(String(2000), default="")
    error: Mapped[str | None] = mapped_column(String(2000))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    submitted_at: Mapped[datetime | None]
    approved_at: Mapped[datetime | None]
    online_at: Mapped[datetime | None]
    retired_at: Mapped[datetime | None]

    model: Mapped[RiskModel] = relationship(back_populates="versions")
    dataset: Mapped[Dataset | None] = relationship(lazy="joined")
    author: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="joined")
    submitter: Mapped[User | None] = relationship(foreign_keys=[submitted_by], lazy="joined")
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by], lazy="joined")
    reviews: Mapped[list["ModelReview"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="ModelReview.id"
    )


class ModelReview(Base):
    """One lifecycle step of a version: submit, approve, reject, online, retire."""

    __tablename__ = "model_reviews"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    comment: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    version: Mapped[ModelVersion] = relationship(back_populates="reviews")
    actor: Mapped[User | None] = relationship(lazy="joined")


# ---- P4: strategies, watchlists, API tokens and decisions ----------------------------------


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128))
    scene: Mapped[str] = mapped_column(String(16), default="admission")
    description: Mapped[str] = mapped_column(String(2000), default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")
    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan", order_by="StrategyVersion.version.desc()"
    )


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version"),
        Index("uq_strategy_online", "strategy_id", unique=True, postgresql_where=text("status = 'online'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    status: Mapped[str] = mapped_column(
        String(16), default="draft"
    )  # draft|in_review|approved|online|retired
    definition: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"default_decision", "rules": [...]}
    backtest: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[str] = mapped_column(String(2000), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    submitted_at: Mapped[datetime | None]
    approved_at: Mapped[datetime | None]
    online_at: Mapped[datetime | None]
    retired_at: Mapped[datetime | None]

    strategy: Mapped[Strategy] = relationship(back_populates="versions")
    author: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="joined")
    submitter: Mapped[User | None] = relationship(foreign_keys=[submitted_by], lazy="joined")
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by], lazy="joined")
    reviews: Mapped[list["StrategyReview"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="StrategyReview.id"
    )


class StrategyReview(Base):
    __tablename__ = "strategy_reviews"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    comment: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    version: Mapped[StrategyVersion] = relationship(back_populates="reviews")
    actor: Mapped[User | None] = relationship(lazy="joined")


class RiskList(Base):
    """A black, white or grey list of identifiers (phones, ID numbers, devices, ...)."""

    __tablename__ = "risk_lists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="black")  # black|white|gray
    dimension: Mapped[str] = mapped_column(String(16), default="phone")  # phone|id_no|device|ip|company|other
    description: Mapped[str] = mapped_column(String(1000), default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")


class RiskListItem(Base):
    """One listed value, stored as an HMAC digest plus a masked form for display."""

    __tablename__ = "risk_list_items"
    __table_args__ = (UniqueConstraint("list_id", "value_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_lists.id", ondelete="CASCADE"), index=True)
    value_hash: Mapped[str] = mapped_column(String(64))
    value_masked: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500), default="")
    expires_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    author: Mapped[User | None] = relationship(lazy="joined")


class ApiToken(Base):
    """A bearer token for machine callers of the decision API; only its digest is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")


class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    strategy_code: Mapped[str] = mapped_column(String(64))
    version: Mapped[int]
    decision: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    hit_rules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    latency_ms: Mapped[float] = mapped_column(default=0.0)
    source: Mapped[str] = mapped_column(String(16), default="api")  # api|console|demo
    token_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("api_tokens.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


# ---- P5: monitors, runs and alerts --------------------------------------------------------


class Monitor(Base):
    """A scheduled check of one model, strategy or set of indicators against thresholds."""

    __tablename__ = "monitors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    # indicator_psi | score_psi | model_ks | approval_rate | rule_hit_rate
    kind: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_models.id", ondelete="CASCADE"), index=True
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    thresholds: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"warn": x, "alert": y}
    schedule: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"freq", "hour", "minute", "weekday"}
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(index=True)
    last_run_at: Mapped[datetime | None]
    last_level: Mapped[str | None] = mapped_column(String(16))  # normal | warn | alert | error
    last_value: Mapped[float | None]
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped[User | None] = relationship(lazy="joined")
    model: Mapped["RiskModel | None"] = relationship(lazy="joined")
    strategy: Mapped["Strategy | None"] = relationship(lazy="joined")
    dataset: Mapped[Dataset | None] = relationship(lazy="joined")


class MonitorRun(Base):
    """One evaluation of a monitor: the headline value, its level and the series behind it."""

    __tablename__ = "monitor_runs"
    __table_args__ = (Index("ix_monitor_runs_monitor_created", "monitor_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(String(16))  # schedule | manual | seed
    status: Mapped[str] = mapped_column(String(16))  # done | failed
    level: Mapped[str] = mapped_column(String(16))  # normal | warn | alert | error
    value: Mapped[float | None]
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(String(2000))
    seconds: Mapped[float] = mapped_column(default=0.0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @property
    def code(self) -> str | None:
        """The error code of a failed run (for example ``too_few_requests``)."""
        return (self.detail or {}).get("code") if self.status == "failed" else None


class Alert(Base):
    """An open problem raised by a monitor; one unresolved alert per monitor, updated by later runs."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("uq_alert_active", "monitor_id", unique=True, postgresql_where=text("status <> 'resolved'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("monitor_runs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|acknowledged|resolved
    level: Mapped[str] = mapped_column(String(16))  # warn | alert (the latest)
    peak_level: Mapped[str] = mapped_column(String(16))
    value: Mapped[float | None]
    threshold: Mapped[float | None]
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)  # headline facts of the latest run
    occurrences: Mapped[int] = mapped_column(default=1)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[datetime | None]
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None]
    resolution: Mapped[str | None] = mapped_column(String(16))  # manual | recovered
    note: Mapped[str] = mapped_column(String(1000), default="")
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    monitor: Mapped[Monitor] = relationship(lazy="joined")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="joined")
    resolver: Mapped[User | None] = relationship(foreign_keys=[resolved_by], lazy="joined")
