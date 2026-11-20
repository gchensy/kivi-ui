"""Risk models: versions trained in the background, a review lifecycle and batch scoring."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select

from .. import audit, jobs
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..model_schemas import (
    JobOut,
    ModelCreateIn,
    ModelDetail,
    ModelOut,
    ModelUpdateIn,
    ReviewIn,
    ScoreIn,
    VersionCreateIn,
    VersionDetail,
    VersionSummary,
)
from ..models import Indicator, Job, ModelReview, ModelVersion, RiskModel, Role
from ..rules import runtime
from .datasets import ensure_owner, get_dataset
from .lifecycle import transition

router = APIRouter(tags=["models"])


def get_model(db: Db, model_id: uuid.UUID) -> RiskModel:
    model = db.get(RiskModel, model_id)
    if model is None:
        raise ApiError(404, "model_not_found", "Model not found")
    return model


def get_version(db: Db, version_id: uuid.UUID) -> ModelVersion:
    version = db.get(ModelVersion, version_id)
    if version is None:
        raise ApiError(404, "version_not_found", "Model version not found")
    return version


def summarise(model: RiskModel) -> ModelOut:
    out = ModelOut.model_validate(model)
    online = next((v for v in model.versions if v.status == "online"), None)
    latest = model.versions[0] if model.versions else None
    return out.model_copy(
        update={
            "version_count": len(model.versions),
            "online": VersionSummary.model_validate(online) if online else None,
            "latest": VersionSummary.model_validate(latest) if latest else None,
        }
    )


@router.get("/models", response_model=list[ModelOut])
def list_models(_: CurrentUser, db: Db) -> list[ModelOut]:
    models = db.scalars(select(RiskModel).order_by(RiskModel.updated_at.desc())).unique().all()
    return [summarise(m) for m in models]


@router.post("/models", response_model=ModelDetail, status_code=status.HTTP_201_CREATED)
def create_model(body: ModelCreateIn, request: Request, user: CurrentUser, db: Db) -> ModelDetail:
    if db.scalar(select(RiskModel.id).where(RiskModel.code == body.code)):
        raise ApiError(409, "code_taken", "A model with this code already exists")
    model = RiskModel(**body.model_dump(), owner_id=user.id)
    db.add(model)
    db.flush()
    audit.record(
        db,
        "model.created",
        actor=user,
        request=request,
        entity_type="model",
        entity_id=model.id,
        code=model.code,
    )
    db.commit()
    db.refresh(model)
    return ModelDetail(**summarise(model).model_dump(), versions=[])


@router.get("/models/{model_id}", response_model=ModelDetail)
def get_one(model_id: uuid.UUID, _: CurrentUser, db: Db) -> ModelDetail:
    model = get_model(db, model_id)
    return ModelDetail(
        **summarise(model).model_dump(), versions=[VersionSummary.model_validate(v) for v in model.versions]
    )


@router.patch("/models/{model_id}", response_model=ModelDetail)
def update_model(
    model_id: uuid.UUID, body: ModelUpdateIn, request: Request, user: CurrentUser, db: Db
) -> ModelDetail:
    model = get_model(db, model_id)
    ensure_owner(user, model.owner_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(model, key, value.strip() if isinstance(value, str) else value)
    audit.record(
        db,
        "model.updated",
        actor=user,
        request=request,
        entity_type="model",
        entity_id=model.id,
        code=model.code,
        fields=sorted(changes),
    )
    db.commit()
    return get_one(model_id, user, db)


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    model = get_model(db, model_id)
    ensure_owner(user, model.owner_id)
    if any(v.status == "online" for v in model.versions):
        raise ApiError(409, "model_online", "Retire the online version before deleting the model")
    code = model.code
    db.delete(model)
    audit.record(
        db, "model.deleted", actor=user, request=request, entity_type="model", entity_id=model_id, code=code
    )
    db.commit()


@router.post("/models/{model_id}/versions", response_model=VersionDetail, status_code=status.HTTP_201_CREATED)
def train_version(
    model_id: uuid.UUID, body: VersionCreateIn, request: Request, user: CurrentUser, db: Db
) -> ModelVersion:
    model = get_model(db, model_id)
    dataset = get_dataset(db, body.dataset_id)
    if not dataset.target_column:
        raise ApiError(400, "no_target", "Choose the target column of this dataset first")
    found = db.scalars(select(Indicator).where(Indicator.id.in_(body.indicator_ids))).unique().all()
    foreign = [i.code for i in found if i.dataset_id != dataset.id]
    if len(found) != len(set(body.indicator_ids)) or foreign:
        raise ApiError(
            400,
            "invalid_indicators",
            "Every indicator must come from the training dataset",
            {"codes": foreign},
        )
    number = (
        db.scalar(select(func.max(ModelVersion.version)).where(ModelVersion.model_id == model.id)) or 0
    ) + 1
    version = ModelVersion(
        model_id=model.id,
        version=number,
        status="training",
        dataset_id=dataset.id,
        config={"indicator_ids": [str(i) for i in body.indicator_ids], "train": body.config.model_dump()},
        notes=body.notes.strip(),
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    job = jobs.enqueue(db, "train_model", {"version_id": str(version.id)}, user)
    version.job_id = job.id
    model.updated_at = datetime.now(UTC)
    audit.record(
        db,
        "version.trained",
        actor=user,
        request=request,
        entity_type="model",
        entity_id=model.id,
        code=model.code,
        version=number,
    )
    db.commit()
    db.refresh(version)
    return version


@router.get("/model-versions/{version_id}", response_model=VersionDetail)
def get_version_detail(version_id: uuid.UUID, _: CurrentUser, db: Db) -> ModelVersion:
    return get_version(db, version_id)


@router.delete("/model-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(version_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    version = get_version(db, version_id)
    ensure_owner(user, version.created_by)
    if version.status not in ("draft", "failed"):
        raise ApiError(409, "invalid_transition", "Only draft or failed versions can be deleted")
    model, number = version.model, version.version
    db.delete(version)
    audit.record(
        db,
        "version.deleted",
        actor=user,
        request=request,
        entity_type="model",
        entity_id=model.id,
        code=model.code,
        version=number,
    )
    db.commit()


@router.post(
    "/model-versions/{version_id}/score", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED
)
def score(version_id: uuid.UUID, body: ScoreIn, request: Request, user: CurrentUser, db: Db) -> Job:
    version = get_version(db, version_id)
    if version.status in ("training", "failed"):
        raise ApiError(409, "invalid_transition", "Only trained versions can score data")
    get_dataset(db, body.dataset_id)
    job = jobs.enqueue(
        db, "score_dataset", {"version_id": str(version.id), "dataset_id": str(body.dataset_id)}, user
    )
    audit.record(
        db,
        "version.scored",
        actor=user,
        request=request,
        entity_type="model",
        entity_id=version.model_id,
        code=version.model.code,
        version=version.version,
    )
    db.commit()
    db.refresh(job)
    return job


@router.post("/model-versions/{version_id}/{action}", response_model=VersionDetail)
def review(
    version_id: uuid.UUID, action: str, body: ReviewIn, request: Request, user: CurrentUser, db: Db
) -> ModelVersion:
    version = get_version(db, version_id)
    was_online = version.status == "online"
    transition(db, version, action, user, body.comment, parent="model_id", review_cls=ModelReview)
    # Retiring the only online version would break every strategy that scores with it.
    if action == "retire" and was_online:
        if users := runtime.online_strategies_using(db, "models", version.model.code):
            raise ApiError(409, "model_in_use", "An online strategy uses this model", {"strategies": users})
    version.model.updated_at = datetime.now(UTC)
    audit.record(
        db,
        f"version.{action}",
        actor=user,
        request=request,
        entity_type="model",
        entity_id=version.model_id,
        code=version.model.code,
        version=version.version,
    )
    db.commit()
    if action in ("online", "retire"):
        runtime.invalidate()  # strategies score with whichever version is online
    db.refresh(version)
    return version


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: CurrentUser, db: Db) -> Job:
    job = db.get(Job, job_id)
    if job is None or (user.role is not Role.admin and job.created_by != user.id):
        raise ApiError(404, "job_not_found", "Job not found")
    return job
