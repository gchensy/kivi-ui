"""Monitors (configure, schedule, run now), their runs, and the alert centre."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from .. import audit
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..models import Alert, Dataset, Indicator, ModelVersion, Monitor, MonitorRun, RiskModel, Strategy
from ..monitor_schemas import (
    AlertAction,
    AlertBrief,
    AlertOut,
    AlertPage,
    MonitorDetail,
    MonitorIn,
    MonitorOut,
    MonitorUpdate,
    RunDetail,
    RunOut,
)
from ..monitoring.checks import DEFAULT_THRESHOLDS
from ..monitoring.schedule import next_run
from ..monitoring.service import _event, run_monitor
from .datasets import ensure_owner

router = APIRouter(tags=["monitoring"])
MODEL_KINDS = {"score_psi", "model_ks"}
STRATEGY_KINDS = {"approval_rate", "rule_hit_rate"}


def get_monitor(db: Session, monitor_id: uuid.UUID) -> Monitor:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise ApiError(404, "monitor_not_found", "Monitor not found")
    return monitor


def latest_runs(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, MonitorRun]:
    """The most recent successful run of each monitor."""
    if not ids:
        return {}
    rows = db.scalars(
        select(MonitorRun)
        .where(MonitorRun.monitor_id.in_(ids), MonitorRun.status == "done")
        .ext(distinct_on(MonitorRun.monitor_id))
        .order_by(MonitorRun.monitor_id, MonitorRun.created_at.desc(), MonitorRun.id.desc())
    ).all()
    return {r.monitor_id: r for r in rows}


def active_alerts(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Alert]:
    if not ids:
        return {}
    rows = db.scalars(select(Alert).where(Alert.monitor_id.in_(ids), Alert.status != "resolved")).unique()
    return {a.monitor_id: a for a in rows}


def trend(db: Session, monitor: Monitor, run: MonitorRun | None) -> list[float | None]:
    """A sparkline: the series of the latest run, or the values of recent runs."""
    if run is not None and run.detail.get("series"):
        return [s.get("value") for s in run.detail["series"]][-12:]
    values = db.scalars(
        select(MonitorRun.value)
        .where(MonitorRun.monitor_id == monitor.id, MonitorRun.status == "done")
        .order_by(MonitorRun.created_at.desc(), MonitorRun.id.desc())
        .limit(12)
    ).all()
    return list(reversed(values))


def outs(db: Session, monitors: list[Monitor]) -> list[MonitorOut]:
    ids = [m.id for m in monitors]
    runs, alerts = latest_runs(db, ids), active_alerts(db, ids)
    result = []
    for m in monitors:
        alert = alerts.get(m.id)
        result.append(
            MonitorOut.model_validate(m).model_copy(
                update={
                    "trend": trend(db, m, runs.get(m.id)),
                    "alert": AlertBrief(id=alert.id, status=alert.status, level=alert.level)
                    if alert
                    else None,
                }
            )
        )
    return result


def detail(db: Session, monitor: Monitor) -> MonitorDetail:
    base = outs(db, [monitor])[0]
    runs = db.scalars(
        select(MonitorRun)
        .where(MonitorRun.monitor_id == monitor.id)
        .order_by(MonitorRun.created_at.desc(), MonitorRun.id.desc())
        .limit(30)
    ).all()
    latest = latest_runs(db, [monitor.id]).get(monitor.id)
    return MonitorDetail(
        **base.model_dump(),
        latest=RunDetail.model_validate(latest) if latest else None,
        runs=[RunOut.model_validate(r) for r in runs],
    )


def _check_targets(db: Session, kind: str, model_id, strategy_id, dataset_id, indicator_ids) -> None:
    if kind in MODEL_KINDS or kind == "indicator_psi":
        if strategy_id:
            raise ApiError(422, "invalid_target", "This check takes a model or indicators, not a strategy")
        if kind in MODEL_KINDS and not model_id:
            raise ApiError(422, "model_required", "Choose the model to monitor")
        if kind == "indicator_psi" and not (model_id or indicator_ids):
            raise ApiError(422, "indicators_required", "Choose a model or indicators to monitor")
        if not dataset_id:
            raise ApiError(422, "dataset_required", "Choose a dataset for this monitor")
    if kind in STRATEGY_KINDS:
        if model_id or dataset_id or indicator_ids:
            raise ApiError(422, "invalid_target", "Decision checks take a strategy only")
        if not strategy_id:
            raise ApiError(422, "strategy_required", "Choose the strategy to monitor")
    if model_id and db.get(RiskModel, model_id) is None:
        raise ApiError(404, "model_not_found", "Model not found")
    if strategy_id and db.get(Strategy, strategy_id) is None:
        raise ApiError(404, "strategy_not_found", "Strategy not found")
    if dataset_id and db.get(Dataset, dataset_id) is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    if indicator_ids:
        found = set(db.scalars(select(Indicator.id).where(Indicator.id.in_(indicator_ids))))
        if missing := [str(i) for i in indicator_ids if i not in found]:
            raise ApiError(404, "indicator_not_found", "Indicator not found", {"ids": missing})


# ---- Monitors ----------------------------------------------------------------------------------


@router.get("/monitors", response_model=list[MonitorOut])
def list_monitors(
    _: CurrentUser,
    db: Db,
    model_id: uuid.UUID | None = None,
    strategy_id: uuid.UUID | None = None,
) -> list[MonitorOut]:
    query = select(Monitor).order_by(Monitor.created_at)
    if model_id:
        query = query.where(Monitor.model_id == model_id)
    if strategy_id:
        query = query.where(Monitor.strategy_id == strategy_id)
    return outs(db, list(db.scalars(query).unique()))


@router.post("/monitors", response_model=MonitorDetail, status_code=status.HTTP_201_CREATED)
def create_monitor(body: MonitorIn, request: Request, user: CurrentUser, db: Db) -> MonitorDetail:
    dataset_id = body.dataset_id
    if body.kind in MODEL_KINDS | {"indicator_psi"} and body.model_id and not dataset_id:
        # Default to the sample the online version was trained on.
        version = db.scalar(
            select(ModelVersion).where(
                ModelVersion.model_id == body.model_id, ModelVersion.status == "online"
            )
        )
        dataset_id = version.dataset_id if version else None
    _check_targets(db, body.kind, body.model_id, body.strategy_id, dataset_id, body.params.indicator_ids)
    if body.params.indicator_ids and body.kind != "indicator_psi":
        raise ApiError(422, "invalid_target", "Only indicator checks take indicators")
    monitor = Monitor(
        name=body.name.strip(),
        kind=body.kind,
        model_id=body.model_id,
        strategy_id=body.strategy_id,
        dataset_id=dataset_id,
        params=body.params.model_dump(mode="json", exclude_none=True),
        thresholds=(body.thresholds.model_dump() if body.thresholds else DEFAULT_THRESHOLDS[body.kind]),
        schedule=body.schedule.model_dump(),
        enabled=body.enabled,
        next_run_at=next_run(body.schedule) if body.enabled else None,
        owner_id=user.id,
    )
    db.add(monitor)
    db.flush()
    audit.record(
        db,
        "monitor.created",
        actor=user,
        request=request,
        entity_type="monitor",
        entity_id=monitor.id,
        name=monitor.name,
        kind=monitor.kind,
    )
    db.commit()
    db.refresh(monitor)
    return detail(db, monitor)


@router.get("/monitors/{monitor_id}", response_model=MonitorDetail)
def get_one(monitor_id: uuid.UUID, _: CurrentUser, db: Db) -> MonitorDetail:
    return detail(db, get_monitor(db, monitor_id))


@router.patch("/monitors/{monitor_id}", response_model=MonitorDetail)
def update_monitor(
    monitor_id: uuid.UUID, body: MonitorUpdate, request: Request, user: CurrentUser, db: Db
) -> MonitorDetail:
    monitor = get_monitor(db, monitor_id)
    ensure_owner(user, monitor.owner_id)
    fields = body.model_dump(exclude_unset=True)
    params = body.params if "params" in fields else None
    dataset_id = body.dataset_id if "dataset_id" in fields else monitor.dataset_id
    indicator_ids = params.indicator_ids if params else monitor.params.get("indicator_ids", [])
    _check_targets(db, monitor.kind, monitor.model_id, monitor.strategy_id, dataset_id, indicator_ids)
    if body.name is not None:
        monitor.name = body.name.strip()
    monitor.dataset_id = dataset_id
    if params is not None:
        monitor.params = params.model_dump(mode="json", exclude_none=True)
    if body.thresholds is not None:
        monitor.thresholds = body.thresholds.model_dump()
    if body.schedule is not None:
        monitor.schedule = body.schedule.model_dump()
    if body.enabled is not None:
        monitor.enabled = body.enabled
    monitor.next_run_at = next_run(monitor.schedule) if monitor.enabled else None
    audit.record(
        db,
        "monitor.updated",
        actor=user,
        request=request,
        entity_type="monitor",
        entity_id=monitor.id,
        name=monitor.name,
        fields=sorted(fields),
    )
    db.commit()
    db.refresh(monitor)
    return detail(db, monitor)


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(monitor_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    monitor = get_monitor(db, monitor_id)
    ensure_owner(user, monitor.owner_id)
    name = monitor.name
    db.delete(monitor)
    audit.record(
        db,
        "monitor.deleted",
        actor=user,
        request=request,
        entity_type="monitor",
        entity_id=monitor_id,
        name=name,
    )
    db.commit()


@router.post("/monitors/{monitor_id}/run", response_model=MonitorDetail)
def run_now(monitor_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> MonitorDetail:
    """Run the check now and return the monitor with the new run (failures are recorded, not raised)."""
    monitor = get_monitor(db, monitor_id)
    run = run_monitor(db, monitor, "manual", user)
    audit.record(
        db,
        "monitor.run",
        actor=user,
        request=request,
        entity_type="monitor",
        entity_id=monitor_id,
        name=monitor.name,
        level=run.level,
    )
    db.commit()
    return detail(db, get_monitor(db, monitor_id))


@router.get("/monitor-runs/{run_id}", response_model=RunDetail)
def get_run(run_id: int, _: CurrentUser, db: Db) -> MonitorRun:
    run = db.get(MonitorRun, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "Monitor run not found")
    return run


# ---- Alerts --------------------------------------------------------------------------------------


def get_alert(db: Session, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise ApiError(404, "alert_not_found", "Alert not found")
    return alert


def alert_counts(db: Session) -> dict[str, int]:
    counts = {"open": 0, "acknowledged": 0, "resolved": 0, "warn": 0, "alert": 0}
    counts.update(dict(db.execute(select(Alert.status, func.count()).group_by(Alert.status)).all()))
    active = db.execute(
        select(Alert.level, func.count()).where(Alert.status != "resolved").group_by(Alert.level)
    ).all()
    counts.update(dict(active))
    return counts


@router.get("/alerts", response_model=AlertPage)
def list_alerts(
    _: CurrentUser,
    db: Db,
    status_: str | None = Query(None, alias="status", pattern="^(open|acknowledged|resolved|active)$"),
    level: str | None = Query(None, pattern="^(warn|alert)$"),
    monitor_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> AlertPage:
    return alert_page(db, status_, level, monitor_id, page, size)


def alert_page(
    db: Session,
    status_: str | None = None,
    level: str | None = None,
    monitor_id: uuid.UUID | None = None,
    page: int = 1,
    size: int = 20,
) -> AlertPage:
    """Unresolved first, then the more severe, then the most recently seen."""
    query = select(Alert)
    if status_ == "active":
        query = query.where(Alert.status != "resolved")
    elif status_:
        query = query.where(Alert.status == status_)
    if level:
        query = query.where(Alert.level == level)
    if monitor_id:
        query = query.where(Alert.monitor_id == monitor_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    severity = case((Alert.level == "alert", 0), else_=1)
    items = (
        db.scalars(
            query.order_by(
                (Alert.status == "resolved").asc(), severity, Alert.last_seen_at.desc(), Alert.id.desc()
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        .unique()
        .all()
    )
    return AlertPage(items=[AlertOut.model_validate(a) for a in items], total=total, counts=alert_counts(db))


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_one_alert(alert_id: int, _: CurrentUser, db: Db) -> Alert:
    return get_alert(db, alert_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(alert_id: int, body: AlertAction, request: Request, user: CurrentUser, db: Db) -> Alert:
    """Claim an open alert: it is assigned to the caller."""
    alert = get_alert(db, alert_id)
    if alert.status != "open":
        raise ApiError(
            409, "invalid_transition", "Only open alerts can be acknowledged", {"status": alert.status}
        )
    alert.status, alert.assignee_id, alert.acknowledged_at = "acknowledged", user.id, datetime.now(UTC)
    if body.note.strip():
        alert.note = body.note.strip()
    alert.events = [*alert.events, _event("acknowledged", user, note=body.note.strip())]
    audit.record(
        db,
        "alert.acknowledged",
        actor=user,
        request=request,
        entity_type="alert",
        entity_id=str(alert.id),
        name=alert.monitor.name,
    )
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve(alert_id: int, body: AlertAction, request: Request, user: CurrentUser, db: Db) -> Alert:
    """Close an alert with a note on what was done; a later bad run opens a new one."""
    alert = get_alert(db, alert_id)
    if alert.status == "resolved":
        raise ApiError(409, "invalid_transition", "The alert is already resolved", {"status": alert.status})
    if not body.note.strip():
        raise ApiError(422, "note_required", "Say how the alert was handled", {"fields": ["note"]})
    now = datetime.now(UTC)
    alert.status, alert.resolution, alert.resolved_at, alert.resolved_by = "resolved", "manual", now, user.id
    alert.note = body.note.strip()
    alert.events = [*alert.events, _event("resolved", user, note=alert.note)]
    audit.record(
        db,
        "alert.resolved",
        actor=user,
        request=request,
        entity_type="alert",
        entity_id=str(alert.id),
        name=alert.monitor.name,
    )
    db.commit()
    db.refresh(alert)
    return alert
