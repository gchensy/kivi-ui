"""Pydantic models for risk models, versions, reviews and jobs."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .analytics.training import TrainConfig
from .data_schemas import DatasetRef, Person

Scene = Literal["application", "behavior", "collection", "fraud", "other"]


def _code(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", value):
        raise ValueError("code must be 2-64 characters: letters, digits and '_', starting with a letter")
    return value


ModelCode = Annotated[str, AfterValidator(_code)]


class ModelCreateIn(BaseModel):
    code: ModelCode
    name: str = Field(min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    scene: Scene = "application"
    description: str = Field("", max_length=2000)


class ModelUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    scene: Scene | None = None
    description: str | None = Field(None, max_length=2000)


class VersionCreateIn(BaseModel):
    dataset_id: uuid.UUID
    indicator_ids: list[uuid.UUID] = Field(min_length=1, max_length=60)
    config: TrainConfig = Field(default_factory=TrainConfig)
    notes: str = Field("", max_length=2000)


class ReviewIn(BaseModel):
    comment: str = Field("", max_length=1000)


class ScoreIn(BaseModel):
    dataset_id: uuid.UUID


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    progress: float
    error: str | None
    result: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    version: int
    status: str
    dataset: DatasetRef | None
    feature_count: int
    auc_train: float | None
    auc_test: float | None
    auc_oot: float | None
    ks_train: float | None
    ks_test: float | None
    ks_oot: float | None
    error: str | None
    job_id: uuid.UUID | None
    author: Person | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    online_at: datetime | None
    retired_at: datetime | None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    actor: Person | None
    comment: str
    created_at: datetime


class ModelRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_en: str | None
    scene: str


class VersionDetail(VersionSummary):
    model: ModelRef
    config: dict[str, Any]
    result: dict[str, Any]
    notes: str
    submitter: Person | None
    approver: Person | None
    reviews: list[ReviewOut]


class ModelOut(BaseModel):
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
    online: VersionSummary | None = None
    latest: VersionSummary | None = None


class ModelDetail(ModelOut):
    versions: list[VersionSummary]
