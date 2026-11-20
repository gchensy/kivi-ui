"""Risk analytics computed with kivi on the demonstration sample."""

from typing import Any

from fastapi import APIRouter, Request

from .. import audit
from ..analytics.service import build_demo, demo_snapshot
from ..deps import AdminUser, CurrentUser, Db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/demo")
def get_demo(_: CurrentUser, db: Db) -> dict[str, Any]:
    """KPIs, indicator binning, scorecard performance, stability and alerts."""
    return demo_snapshot(db)


@router.post("/demo/rebuild")
def rebuild_demo(request: Request, admin: AdminUser, db: Db) -> dict[str, Any]:
    payload = build_demo(db)
    audit.record(
        db, "analytics.rebuilt", actor=admin, request=request, entity_type="analytics", entity_id="demo"
    )
    db.commit()
    return payload
