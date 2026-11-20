"""Run monitors, record their runs and keep one alert per monitor up to date.

A warn or alert run opens an alert, or updates the monitor's unresolved one (level, value,
occurrences). A normal run resolves it as recovered. A failed run leaves alerts alone.
Scheduled runs are picked up by the job worker's tick (see ``schedule_due``).
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobs
from ..data.store import DataError
from ..db import get_sessionmaker
from ..models import Alert, Monitor, MonitorRun, User
from .checks import CHECKS, CheckError, level_of
from .schedule import next_run

log = logging.getLogger("kivi_ui.monitoring")
SEVERITY = {"normal": 0, "warn": 1, "alert": 2}


def _now() -> datetime:
    return datetime.now(UTC)


def _event(action: str, user: User | None = None, **extra: Any) -> dict[str, Any]:
    event = {"action": action, "at": _now().isoformat(timespec="seconds")} | extra
    if user is not None:
        event["actor"] = {"id": str(user.id), "display_name": user.display_name}
    return event


def _headline(monitor: Monitor, detail: dict[str, Any]) -> dict[str, Any]:
    """The facts an alert shows without loading the run: period and the worst item."""
    keep = ("period", "worst", "model", "strategy", "auc", "ks", "current", "baseline")
    return {k: detail[k] for k in keep if k in detail}


def run_monitor(db: Session, monitor: Monitor, trigger: str, user: User | None = None) -> MonitorRun:
    """Evaluate `monitor` now and commit the run and any alert change."""
    started = time.perf_counter()
    run = MonitorRun(monitor_id=monitor.id, trigger=trigger, created_by=user.id if user else None)
    try:
        outcome = CHECKS[monitor.kind](db, monitor)
        run.status, run.value, run.detail = "done", outcome.value, outcome.detail
        run.level = level_of(monitor.kind, outcome.value, monitor.thresholds)
    except (CheckError, DataError) as error:
        db.rollback()
        run.status, run.level = "failed", "error"
        run.error = str(error)[:2000]
        run.detail = {"code": getattr(error, "code", "error"), **getattr(error, "detail", {})}
    except Exception as error:  # noqa: BLE001 - a broken check must not stop the scheduler
        db.rollback()
        log.exception("monitor %s failed", monitor.id)
        run.status, run.level = "failed", "error"
        run.error = f"{type(error).__name__}: {error}"[:2000]
        run.detail = {"code": "internal_error"}
    run.seconds = round(time.perf_counter() - started, 3)
    monitor = db.merge(monitor)
    db.add(run)
    db.flush()
    monitor.last_run_at, monitor.last_level = _now(), run.level
    if run.status == "done":
        monitor.last_value = run.value
        _update_alert(db, monitor, run)
    db.commit()
    db.refresh(run)
    return run


def _update_alert(db: Session, monitor: Monitor, run: MonitorRun) -> None:
    # Lock the monitor row: a manual run and a scheduled run of the same monitor take turns here,
    # so the second sees the alert the first opened instead of opening another.
    db.execute(select(Monitor.id).where(Monitor.id == monitor.id).with_for_update())
    active = db.scalar(select(Alert).where(Alert.monitor_id == monitor.id, Alert.status != "resolved"))
    now = _now()
    if run.level in ("warn", "alert"):
        threshold = monitor.thresholds[run.level]
        if active is None:
            db.add(
                Alert(
                    monitor_id=monitor.id,
                    run_id=run.id,
                    status="open",
                    level=run.level,
                    peak_level=run.level,
                    value=run.value,
                    threshold=threshold,
                    detail=_headline(monitor, run.detail),
                    first_seen_at=now,
                    last_seen_at=now,
                    events=[_event("opened", level=run.level, value=run.value)],
                )
            )
            return
        events = list(active.events)
        if SEVERITY[run.level] > SEVERITY[active.level]:
            events.append(_event("escalated", level=run.level, value=run.value))
        elif SEVERITY[run.level] < SEVERITY[active.level]:
            events.append(_event("eased", level=run.level, value=run.value))
        active.level, active.value, active.threshold = run.level, run.value, threshold
        if SEVERITY[run.level] > SEVERITY[active.peak_level]:
            active.peak_level = run.level
        active.run_id, active.detail = run.id, _headline(monitor, run.detail)
        active.occurrences += 1
        active.last_seen_at = now
        active.events = events
    elif active is not None:
        active.status, active.resolution, active.resolved_at = "resolved", "recovered", now
        active.run_id = run.id
        active.events = [*active.events, _event("recovered", value=run.value)]


# ---- Scheduling ------------------------------------------------------------------------------


def due_monitors(db: Session, now: datetime) -> list[Monitor]:
    """Claim enabled monitors whose time has come and move their next run forward."""
    due = (
        db.scalars(
            select(Monitor)
            .where(Monitor.enabled, Monitor.next_run_at.isnot(None), Monitor.next_run_at <= now)
            .order_by(Monitor.next_run_at)
            .with_for_update(skip_locked=True, of=Monitor)
        )
        .unique()
        .all()
    )
    for monitor in due:
        monitor.next_run_at = next_run(monitor.schedule, now)
    db.commit()
    return due


@jobs.tick
def schedule_due() -> int:
    """Run every monitor that is due. Called by the worker about every 30 seconds."""
    maker = get_sessionmaker()
    with maker() as db:
        ids = [m.id for m in due_monitors(db, _now())]
    for monitor_id in ids:
        with maker() as db:
            monitor = db.get(Monitor, monitor_id)
            if monitor is not None:
                run_monitor(db, monitor, "schedule")
    return len(ids)
