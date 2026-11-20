"""Build and store analysis snapshots in PostgreSQL."""

from datetime import date
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import AnalyticsSnapshot
from . import sample, scorecard

DEMO_KEY = "demo"


def build_demo(db: Session, as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    payload = scorecard.build(sample.simulate(as_of), as_of)
    statement = insert(AnalyticsSnapshot).values(key=DEMO_KEY, payload=payload)
    db.execute(
        statement.on_conflict_do_update(index_elements=[AnalyticsSnapshot.key], set_={"payload": payload})
    )
    db.commit()
    return payload


def demo_snapshot(db: Session) -> dict[str, Any]:
    snapshot = db.get(AnalyticsSnapshot, DEMO_KEY)
    return snapshot.payload if snapshot else build_demo(db)
