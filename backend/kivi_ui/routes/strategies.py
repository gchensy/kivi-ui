"""Strategies: versioned rule sets with backtests, a test console and the review lifecycle."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Request, status
from sqlalchemy import func, select

from .. import audit
from ..data import store
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..model_schemas import ReviewIn
from ..models import (
    Dataset,
    Indicator,
    ModelVersion,
    RiskList,
    RiskModel,
    Strategy,
    StrategyReview,
    StrategyVersion,
)
from ..rules import runtime
from ..rules.dsl import Definition, references
from ..rules.engine import evaluate, summarise, swap
from ..strategy_schemas import (
    BacktestIn,
    EvaluateIn,
    FieldOption,
    FieldsOut,
    StrategyCreateIn,
    StrategyDetail,
    StrategyOut,
    StrategyUpdateIn,
    StrategyVersionCreateIn,
    StrategyVersionDetail,
    StrategyVersionSummary,
    StrategyVersionUpdateIn,
)
from .datasets import ensure_owner, get_dataset
from .lifecycle import transition

router = APIRouter(tags=["strategies"])


def get_strategy(db: Db, strategy_id: uuid.UUID) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise ApiError(404, "strategy_not_found", "Strategy not found")
    return strategy


def get_version(db: Db, version_id: uuid.UUID) -> StrategyVersion:
    version = db.get(StrategyVersion, version_id)
    if version is None:
        raise ApiError(404, "version_not_found", "Strategy version not found")
    return version


def summary(version: StrategyVersion) -> StrategyVersionSummary:
    out = StrategyVersionSummary.model_validate(version)
    return out.model_copy(
        update={
            "rule_count": len(version.definition.get("rules", [])),
            "pass_rate": (version.backtest.get("summary") or {}).get("pass_rate"),
        }
    )


def detail(version: StrategyVersion) -> StrategyVersionDetail:
    base = summary(version).model_dump()
    return StrategyVersionDetail(
        **base,
        strategy=version.strategy,
        definition=version.definition,
        backtest=version.backtest,
        submitter=version.submitter,
        approver=version.approver,
        reviews=version.reviews,
    )


def overview(strategy: Strategy) -> StrategyOut:
    online = next((v for v in strategy.versions if v.status == "online"), None)
    latest = strategy.versions[0] if strategy.versions else None
    return StrategyOut.model_validate(strategy).model_copy(
        update={
            "version_count": len(strategy.versions),
            "online": summary(online) if online else None,
            "latest": summary(latest) if latest else None,
        }
    )


@router.get("/strategies", response_model=list[StrategyOut])
def list_strategies(_: CurrentUser, db: Db) -> list[StrategyOut]:
    return [overview(s) for s in db.scalars(select(Strategy).order_by(Strategy.updated_at.desc())).unique()]


@router.post("/strategies", response_model=StrategyDetail, status_code=status.HTTP_201_CREATED)
def create_strategy(body: StrategyCreateIn, request: Request, user: CurrentUser, db: Db) -> StrategyDetail:
    if db.scalar(select(Strategy.id).where(Strategy.code == body.code)):
        raise ApiError(409, "code_taken", "A strategy with this code already exists")
    strategy = Strategy(**body.model_dump(), owner_id=user.id)
    db.add(strategy)
    db.flush()
    db.add(
        StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            definition=Definition().model_dump(),
            created_by=user.id,
            notes="",
        )
    )
    audit.record(
        db,
        "strategy.created",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=strategy.id,
        code=strategy.code,
    )
    db.commit()
    db.refresh(strategy)
    return StrategyDetail(**overview(strategy).model_dump(), versions=[summary(v) for v in strategy.versions])


@router.get("/strategies/fields", response_model=FieldsOut)
def fields(_: CurrentUser, db: Db, dataset_id: uuid.UUID | None = None) -> FieldsOut:
    """Suggestions for the rule editor: dataset columns, indicators, online model outputs, watchlists."""
    options: dict[str, FieldOption] = {}
    for indicator in db.scalars(select(Indicator).order_by(Indicator.code)).unique():
        options.setdefault(
            indicator.code,
            FieldOption(name=indicator.code, label=indicator.name, dtype=indicator.kind, source="indicator"),
        )
    if dataset_id:
        dataset = get_dataset(db, dataset_id)
        for column in dataset.columns:
            if column.role != "target":
                options.setdefault(
                    column.column_name,
                    FieldOption(
                        name=column.column_name, label=column.name, dtype=column.dtype, source="column"
                    ),
                )
    models = []
    for code, name, name_en, version in db.execute(
        select(RiskModel.code, RiskModel.name, RiskModel.name_en, ModelVersion.version)
        .join(ModelVersion, ModelVersion.model_id == RiskModel.id)
        .where(ModelVersion.status == "online")
    ):
        models.append({"code": code, "name": name, "name_en": name_en, "version": version})
        for output in ("score", "prob"):
            key = f"model:{code}.{output}"
            options[key] = FieldOption(name=key, label=f"{name} · {output}", dtype="numeric", source="model")
    lists = [
        {
            "code": lst.code,
            "name": lst.name,
            "name_en": lst.name_en,
            "kind": lst.kind,
            "dimension": lst.dimension,
        }
        for lst in db.scalars(select(RiskList).order_by(RiskList.code)).unique()
    ]
    return FieldsOut(fields=list(options.values()), models=models, lists=lists)


@router.get("/strategies/{strategy_id}", response_model=StrategyDetail)
def get_one(strategy_id: uuid.UUID, _: CurrentUser, db: Db) -> StrategyDetail:
    strategy = get_strategy(db, strategy_id)
    return StrategyDetail(**overview(strategy).model_dump(), versions=[summary(v) for v in strategy.versions])


@router.patch("/strategies/{strategy_id}", response_model=StrategyDetail)
def update_strategy(
    strategy_id: uuid.UUID, body: StrategyUpdateIn, request: Request, user: CurrentUser, db: Db
) -> StrategyDetail:
    strategy = get_strategy(db, strategy_id)
    ensure_owner(user, strategy.owner_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(strategy, key, value.strip() if isinstance(value, str) else value)
    audit.record(
        db,
        "strategy.updated",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=strategy.id,
        code=strategy.code,
        fields=sorted(changes),
    )
    db.commit()
    return get_one(strategy_id, user, db)


@router.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(strategy_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    strategy = get_strategy(db, strategy_id)
    ensure_owner(user, strategy.owner_id)
    if any(v.status == "online" for v in strategy.versions):
        raise ApiError(409, "strategy_online", "Retire the online version before deleting the strategy")
    code = strategy.code
    db.delete(strategy)
    audit.record(
        db,
        "strategy.deleted",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=strategy_id,
        code=code,
    )
    db.commit()
    runtime.invalidate(code)


@router.post(
    "/strategies/{strategy_id}/versions",
    response_model=StrategyVersionDetail,
    status_code=status.HTTP_201_CREATED,
)
def new_version(
    strategy_id: uuid.UUID, body: StrategyVersionCreateIn, request: Request, user: CurrentUser, db: Db
) -> StrategyVersionDetail:
    strategy = get_strategy(db, strategy_id)
    if body.definition is not None:
        definition = body.definition.model_dump()
    elif body.copy_from is not None:
        source = get_version(db, body.copy_from)
        if source.strategy_id != strategy.id:
            raise ApiError(400, "version_not_found", "Copy from a version of the same strategy")
        definition = source.definition
    else:
        definition = strategy.versions[0].definition if strategy.versions else Definition().model_dump()
    number = (
        db.scalar(select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_id == strategy.id))
        or 0
    ) + 1
    version = StrategyVersion(
        strategy_id=strategy.id,
        version=number,
        definition=definition,
        notes=body.notes.strip(),
        created_by=user.id,
    )
    db.add(version)
    strategy.updated_at = datetime.now(UTC)
    db.flush()
    audit.record(
        db,
        "strategy_version.created",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=strategy.id,
        code=strategy.code,
        version=number,
    )
    db.commit()
    db.refresh(version)
    return detail(version)


@router.get("/strategy-versions/{version_id}", response_model=StrategyVersionDetail)
def get_version_detail(version_id: uuid.UUID, _: CurrentUser, db: Db) -> StrategyVersionDetail:
    return detail(get_version(db, version_id))


@router.put("/strategy-versions/{version_id}", response_model=StrategyVersionDetail)
def save_rules(
    version_id: uuid.UUID, body: StrategyVersionUpdateIn, request: Request, user: CurrentUser, db: Db
) -> StrategyVersionDetail:
    version = get_version(db, version_id)
    ensure_owner(user, version.created_by)
    if version.status != "draft":
        raise ApiError(409, "invalid_transition", "Only draft versions can be edited")
    version.definition = body.definition.model_dump()
    version.backtest = {}
    if body.notes is not None:
        version.notes = body.notes.strip()
    audit.record(
        db,
        "strategy_version.updated",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=version.strategy_id,
        code=version.strategy.code,
        version=version.version,
        rules=len(body.definition.rules),
    )
    db.commit()
    db.refresh(version)
    return detail(version)


@router.delete("/strategy-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(version_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    version = get_version(db, version_id)
    ensure_owner(user, version.created_by)
    if version.status != "draft":
        raise ApiError(409, "invalid_transition", "Only draft versions can be deleted")
    strategy, number = version.strategy, version.version
    db.delete(version)
    audit.record(
        db,
        "strategy_version.deleted",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=strategy.id,
        code=strategy.code,
        version=number,
    )
    db.commit()


def dataset_frame(db: Db, dataset: Dataset) -> tuple[pd.DataFrame, pd.Series | None, pd.Series | None]:
    """All columns under their SQL names, plus header aliases; labels and months when available."""
    frame = store.read_columns(db, dataset, [c.column_name for c in dataset.columns])
    for column in dataset.columns:
        if column.name != column.column_name and column.name not in frame.columns:
            frame[column.name] = frame[column.column_name]
    y = store.labels(dataset, frame) if dataset.target_column else None
    months = None
    if dataset.date_column:
        months = (
            pd.to_datetime(frame[dataset.date_column], errors="coerce").dt.to_period("M").astype("string")
        )
    return frame, y, months


@router.post("/strategy-versions/{version_id}/backtest", response_model=StrategyVersionDetail)
def backtest(
    version_id: uuid.UUID, body: BacktestIn, request: Request, user: CurrentUser, db: Db
) -> StrategyVersionDetail:
    version = get_version(db, version_id)
    dataset = get_dataset(db, body.dataset_id)
    started = time.perf_counter()
    frame, y, months = dataset_frame(db, dataset)
    definition = Definition.model_validate(version.definition)
    result = evaluate(definition, frame, runtime.context_for(db, definition))
    labelled = y.notna() if y is not None else None
    y_eval = y[labelled].astype(int) if y is not None else None
    payload: dict[str, Any] = {
        "dataset": {"id": str(dataset.id), "name": dataset.name},
        "summary": summarise(definition, result, y, months),
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if body.compare_version_id:
        other = get_version(db, body.compare_version_id)
        other_definition = Definition.model_validate(other.definition)
        other_result = evaluate(other_definition, frame, runtime.context_for(db, other_definition))
        payload["compare"] = {
            "version_id": str(other.id),
            "version": other.version,
            "summary": summarise(other_definition, other_result, y, months),
            "swap": swap(
                other_result.decision[labelled] if y is not None else other_result.decision,
                result.decision[labelled] if y is not None else result.decision,
                y_eval,
            ),
        }
    payload["seconds"] = round(time.perf_counter() - started, 3)
    version.backtest = payload
    audit.record(
        db,
        "strategy_version.backtested",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=version.strategy_id,
        code=version.strategy.code,
        version=version.version,
        name=dataset.name,
    )
    db.commit()
    db.refresh(version)
    return detail(version)


@router.post("/strategy-versions/{version_id}/evaluate")
def evaluate_one(version_id: uuid.UUID, body: EvaluateIn, _: CurrentUser, db: Db) -> dict[str, Any]:
    """Run one record through any version (the test console); nothing is logged."""
    version = get_version(db, version_id)
    definition = Definition.model_validate(version.definition)
    started = time.perf_counter()
    result = evaluate(definition, pd.DataFrame([body.data]), runtime.context_for(db, definition), trace=True)
    return response_body(
        definition,
        result,
        f"console-{uuid.uuid4().hex[:12]}",
        {"code": version.strategy.code, "version": version.version},
        (time.perf_counter() - started) * 1000,
    ) | {"trace": result.trace}


def response_body(
    definition: Definition, result, request_id: str, strategy: dict[str, Any], latency_ms: float
) -> dict[str, Any]:
    deciding = result.deciding_rule.iloc[0]
    rules = {r.code: r for r in definition.rules}
    scores: dict[str, dict[str, Any]] = {}
    for column in result.outputs.columns:
        code, output = column[len("model:") :].rsplit(".", 1)
        value = result.outputs[column].iloc[0]
        scores.setdefault(code, {})["score" if output == "score" else "probability"] = (
            int(value) if output == "score" else round(float(value), 6)
        )
    hits = [
        {
            "code": code,
            "name": rules[code].name,
            "name_en": rules[code].name_en,
            "decision": rules[code].decision,
        }
        for code in result.hits.columns
        if bool(result.hits[code].iloc[0])
    ]
    reason = ""
    if deciding:
        reason = rules[deciding].reason or deciding
    return {
        "request_id": request_id,
        "decision": result.decision.iloc[0],
        "reason": reason,
        "rules": hits,
        "scores": scores,
        "strategy": strategy,
        "missing_fields": result.missing_fields,
        "latency_ms": round(latency_ms, 2),
    }


@router.post("/strategy-versions/{version_id}/{action}", response_model=StrategyVersionDetail)
def review(
    version_id: uuid.UUID, action: str, body: ReviewIn, request: Request, user: CurrentUser, db: Db
) -> StrategyVersionDetail:
    version = get_version(db, version_id)
    # Role, state and four-eyes checks come first; a refusal below is rolled back with the session.
    transition(db, version, action, user, body.comment, parent="strategy_id", review_cls=StrategyReview)
    if action == "online":
        definition = Definition.model_validate(version.definition)
        if not definition.rules:
            raise ApiError(409, "empty_strategy", "Add at least one rule before putting a version online")
        refs, ctx = references(definition), runtime.context_for(db, definition)
        if missing := sorted(refs["lists"] - set(ctx.lists)):
            raise ApiError(409, "list_not_found", "A referenced watchlist does not exist", {"lists": missing})
        if missing := sorted(refs["models"] - set(ctx.models)):
            raise ApiError(
                409, "model_not_online", "A referenced model has no online version", {"models": missing}
            )
    version.strategy.updated_at = datetime.now(UTC)
    audit.record(
        db,
        f"strategy_version.{action}",
        actor=user,
        request=request,
        entity_type="strategy",
        entity_id=version.strategy_id,
        code=version.strategy.code,
        version=version.version,
    )
    db.commit()
    runtime.invalidate(version.strategy.code)
    db.refresh(version)
    return detail(version)
