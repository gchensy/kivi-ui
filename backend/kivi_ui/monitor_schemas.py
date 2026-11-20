"""Pydantic models for monitors, monitor runs, alerts, the overview and stability views."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .data_schemas import Person
from .monitoring.schedule import Schedule

Kind = Literal["indicator_psi", "score_psi", "model_ks", "approval_rate", "rule_hit_rate"]
Level = Literal["normal", "warn", "alert", "error"]
AlertStatus = Literal["open", "acknowledged", "resolved"]
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warn: float = Field(ge=0, le=100)
    alert: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> "Thresholds":
        if self.alert < self.warn:
            raise ValueError("the alert threshold must not be below the warning threshold")
        return self


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _month(cls, value: str) -> str:
        if not MONTH.match(value):
            raise ValueError("months look like 2026-01")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> "Reference":
        if self.end < self.start:
            raise ValueError("the reference period ends before it starts")
        return self


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    reference: Reference | None = None
    window_days: int = Field(7, ge=1, le=90)
    baseline_days: int = Field(30, ge=1, le=365)
    min_requests: int = Field(30, ge=1, le=1_000_000)


class MonitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: Kind
    model_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None
    dataset_id: uuid.UUID | None = None
    params: Params = Field(default_factory=Params)
    thresholds: Thresholds | None = None
    schedule: Schedule = Field(default_factory=Schedule)
    enabled: bool = True


class MonitorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    dataset_id: uuid.UUID | None = None
    params: Params | None = None
    thresholds: Thresholds | None = None
    schedule: Schedule | None = None
    enabled: bool | None = None


class Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_en: str | None = None


class DatasetRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    status: str
    level: Level
    value: float | None
    error: str | None
    code: str | None = None
    seconds: float
    created_at: datetime


class RunDetail(RunOut):
    detail: dict[str, Any]


class AlertBrief(BaseModel):
    id: int
    status: AlertStatus
    level: Level


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: Kind
    model: Ref | None
    strategy: Ref | None
    dataset: DatasetRef | None
    params: dict[str, Any]
    thresholds: dict[str, float]
    schedule: dict[str, Any]
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_level: Level | None
    last_value: float | None
    owner: Person | None
    created_at: datetime
    updated_at: datetime
    trend: list[float | None] = Field(default_factory=list)
    alert: AlertBrief | None = None


class MonitorDetail(MonitorOut):
    latest: RunDetail | None = None
    runs: list[RunOut] = Field(default_factory=list)


class MonitorBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: Kind
    model: Ref | None
    strategy: Ref | None
    thresholds: dict[str, float]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor: MonitorBrief
    run_id: int | None
    status: AlertStatus
    level: Level
    peak_level: Level
    value: float | None
    threshold: float | None
    detail: dict[str, Any]
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    assignee: Person | None
    acknowledged_at: datetime | None
    resolver: Person | None
    resolved_at: datetime | None
    resolution: str | None
    note: str
    events: list[dict[str, Any]]


class AlertPage(BaseModel):
    items: list[AlertOut]
    total: int
    counts: dict[str, int]


class AlertAction(BaseModel):
    note: str = Field("", max_length=1000)
