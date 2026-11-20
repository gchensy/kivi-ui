"""Keep demo decisions current: move them forward by whole days as the calendar advances.

``seed-demo`` writes 30 days of decisions ending on the day it runs. Without this, the overview
would empty out and the decision monitors would fail for lack of data a month later. Only rows
with ``source = 'demo'`` are touched; real API decisions never move.
"""

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, cast, func, select, update
from sqlalchemy.orm import Session

from . import jobs
from .db import get_sessionmaker
from .models import DecisionLog
from .monitoring.schedule import zone

CHECK_SECONDS = 3600
_last_check: float | None = None


def roll_demo_decisions(db: Session, now: datetime | None = None) -> int:
    """Shift demo decisions so the newest falls on today (local date). Returns the days moved."""
    now = now or datetime.now(UTC)
    newest = db.scalar(select(func.max(DecisionLog.created_at)).where(DecisionLog.source == "demo"))
    if newest is None:
        return 0
    tz = zone()
    days = (now.astimezone(tz).date() - newest.astimezone(tz).date()).days
    if days < 1:
        return 0
    demo = DecisionLog.source == "demo"
    db.execute(
        update(DecisionLog).where(demo).values(created_at=DecisionLog.created_at + timedelta(days=days))
    )
    # Decisions from later in the day than now stay in the past, spread over the last three hours.
    minutes = func.make_interval(0, 0, 0, 0, 0, cast((DecisionLog.id % 180) + 1, Integer))
    db.execute(update(DecisionLog).where(demo, DecisionLog.created_at > now).values(created_at=now - minutes))
    db.commit()
    return days


@jobs.tick
def roll_tick() -> None:
    """At most once an hour, from the worker."""
    global _last_check
    if _last_check is not None and time.monotonic() - _last_check < CHECK_SECONDS:
        return
    _last_check = time.monotonic()
    with get_sessionmaker()() as db:
        roll_demo_decisions(db)
