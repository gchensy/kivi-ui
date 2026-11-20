"""Pydantic models for strategies, watchlists, API tokens and decisions."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .data_schemas import Person
from .rules.dsl import Decision, Definition

StrategyScene = Literal["admission", "fraud", "limit", "pricing", "behavior", "collection", "other"]
ListKind = Literal["black", "white", "gray"]
Dimension = Literal["phone", "id_no", "device", "ip", "company", "account", "other"]


def _upper_code(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", value):
        raise ValueError("code must be 2-64 characters: letters, digits and '_', starting with a letter")
    return value


UpperCode = Annotated[str, AfterValidator(_upper_code)]


class StrategyCreateIn(BaseModel):
    code: UpperCode
    name: str = Field(min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    scene: StrategyScene = "admission"
    description: str = Field("", max_length=2000)


class StrategyUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    scene: StrategyScene | None = None
    description: str | None = Field(None, max_length=2000)


class StrategyVersionCreateIn(BaseModel):
    definition: Definition | None = None
    copy_from: uuid.UUID | None = None
    notes: str = Field("", max_length=2000)


class StrategyVersionUpdateIn(BaseModel):
    definition: Definition
    notes: str | None = Field(None, max_length=2000)


class BacktestIn(BaseModel):
    dataset_id: uuid.UUID
    compare_version_id: uuid.UUID | None = None


class EvaluateIn(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class StrategyVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    version: int
    status: str
    notes: str
    author: Person | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    online_at: datetime | None
    retired_at: datetime | None
    rule_count: int = 0
    pass_rate: float | None = None


class StrategyRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_en: str | None
    scene: str


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    actor: Person | None
    comment: str
    created_at: datetime


class StrategyVersionDetail(StrategyVersionSummary):
    strategy: StrategyRef
    definition: dict[str, Any]
    backtest: dict[str, Any]
    submitter: Person | None
    approver: Person | None
    reviews: list[ReviewOut]


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_en: str | None
    scene: str
    description: str
    owner: Person | None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    online: StrategyVersionSummary | None = None
    latest: StrategyVersionSummary | None = None


class StrategyDetail(StrategyOut):
    versions: list[StrategyVersionSummary]


class FieldOption(BaseModel):
    name: str
    label: str | None = None
    dtype: str | None = None
    source: Literal["column", "indicator", "model"]


class FieldsOut(BaseModel):
    fields: list[FieldOption]
    models: list[dict[str, Any]]
    lists: list[dict[str, Any]]


# ---- Watchlists -----------------------------------------------------------------------------


class ListCreateIn(BaseModel):
    code: UpperCode
    name: str = Field(min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    kind: ListKind = "black"
    dimension: Dimension = "phone"
    description: str = Field("", max_length=1000)


class ListUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    kind: ListKind | None = None
    description: str | None = Field(None, max_length=1000)


class ListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_en: str | None
    kind: str
    dimension: str
    description: str
    owner: Person | None
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    active_count: int = 0


class ItemsIn(BaseModel):
    values: list[str] = Field(min_length=1, max_length=5000)
    reason: str = Field("", max_length=500)
    expires_at: datetime | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    value_masked: str
    reason: str
    expires_at: datetime | None
    author: Person | None
    created_at: datetime


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int


class AddItemsOut(BaseModel):
    added: int
    skipped: int


class CheckIn(BaseModel):
    value: str = Field(min_length=1, max_length=256)


class CheckOut(BaseModel):
    listed: bool
    item: ItemOut | None = None


# ---- API tokens -----------------------------------------------------------------------------


class TokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    expires_days: int | None = Field(None, ge=1, le=3650)


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    owner: Person | None
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class TokenCreated(TokenOut):
    token: str


# ---- Decisions ------------------------------------------------------------------------------


class DecideIn(BaseModel):
    request_id: str | None = Field(None, pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    data: dict[str, Any] = Field(default_factory=dict)


class RuleHit(BaseModel):
    code: str
    name: str
    name_en: str | None = None
    decision: Decision


class DecideOut(BaseModel):
    request_id: str
    decision: Decision
    reason: str
    rules: list[RuleHit]
    scores: dict[str, dict[str, Any]]
    strategy: dict[str, Any]
    missing_fields: list[str]
    latency_ms: float
    replayed: bool = False


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    strategy_code: str
    version: int
    decision: str
    reason: str
    hit_rules: list[str]
    scores: dict[str, Any]
    latency_ms: float
    source: str
    created_at: datetime


class DecisionDetail(DecisionOut):
    trace: list[dict[str, Any]]
    input: dict[str, Any]


class DecisionPage(BaseModel):
    items: list[DecisionOut]
    total: int
    counts: dict[str, int]
