"""Pydantic models for datasets, indicators and binning schemes."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .analytics.binning import BinSpec

Role = Literal["feature", "target", "id", "date", "ignore"]
Category = Literal["basic", "application", "credit", "transaction", "behavior", "derived", "other"]
IndicatorStatus = Literal["draft", "published", "retired"]
Unit = Literal["count", "ratio", "cny", "years"]


def _code(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", value):
        raise ValueError(
            "code must be 2-64 characters: lowercase letters, digits and '_', starting with a letter"
        )
    return value


Code = Annotated[str, AfterValidator(_code)]


class Person(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    name: str
    column_name: str
    dtype: str
    role: str
    missing_rate: float
    unique_count: int
    iv: float | None
    stats: dict[str, Any]


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    source: str
    file_name: str | None
    row_count: int
    column_count: int
    target_column: str | None
    target_event: str | None
    date_column: str | None
    id_column: str | None
    bad_rate: float | None
    profile: dict[str, Any]
    owner: Person | None
    created_at: datetime
    updated_at: datetime


class DatasetDetail(DatasetOut):
    columns: list[ColumnOut]
    indicator_count: int = 0


class DatasetUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=1000)
    target_column: str | None = None
    target_event: str | None = None
    date_column: str | None = None
    id_column: str | None = None
    roles: dict[str, Role] | None = None
    clear: list[Literal["target_column", "date_column", "id_column"]] = Field(default_factory=list)


class PreviewOut(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total: int


class ScreeningRow(BaseModel):
    column: str
    name: str
    dtype: str
    iv: float | None
    level: str | None
    trend: str | None
    bins: int
    missing_rate: float
    note: str | None
    indicator_id: uuid.UUID | None = None


class SchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    method: str
    spec: dict[str, Any]
    rule: dict[str, Any]
    bins: list[dict[str, Any]]
    iv: float
    trend: str
    missing_rate: float
    dataset_id: uuid.UUID | None
    author: Person | None
    created_at: datetime


class SchemeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    method: str
    iv: float
    trend: str
    created_at: datetime


class DatasetRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    target_column: str | None
    date_column: str | None
    row_count: int


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_en: str | None
    category: str
    description: str
    kind: str
    unit: str | None
    status: str
    column_name: str
    dataset: DatasetRef | None
    default_scheme: SchemeSummary | None
    owner: Person | None
    created_at: datetime
    updated_at: datetime


class IndicatorDetail(IndicatorOut):
    schemes: list[SchemeOut]


class IndicatorPage(BaseModel):
    items: list[IndicatorOut]
    total: int
    counts: dict[str, int]


class IndicatorCreateIn(BaseModel):
    code: Code
    name: str = Field(min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    category: Category = "other"
    description: str = Field("", max_length=2000)
    unit: Unit | None = None
    status: IndicatorStatus = "draft"
    dataset_id: uuid.UUID
    column: str


class IndicatorImportIn(BaseModel):
    dataset_id: uuid.UUID
    columns: list[str] = Field(min_length=1, max_length=300)
    category: Category = "other"


class IndicatorUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    category: Category | None = None
    description: str | None = Field(None, max_length=2000)
    unit: Unit | None = None
    status: IndicatorStatus | None = None
    clear_unit: bool = False


class BinningOut(BaseModel):
    bins: list[dict[str, Any]]
    iv: float
    level: str
    trend: str
    missing_rate: float
    rows: int
    bad_rate: float
    rule: dict[str, Any]
    notes: list[str]


class SchemeCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    spec: BinSpec
    make_default: bool = True


class StabilityMonth(BaseModel):
    month: str
    rows: int
    psi: float | None
    bad_rate: float | None
    in_reference: bool
    shares: dict[str, float]


class StabilityOut(BaseModel):
    scheme_id: uuid.UUID
    reference: list[str]
    months: list[StabilityMonth]
    bins: list[dict[str, Any]]
