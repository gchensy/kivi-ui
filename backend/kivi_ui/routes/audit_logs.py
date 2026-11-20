"""Read-only audit trail for administrators."""

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from ..deps import AdminUser, Db
from ..models import AuditLog
from ..schemas import AuditLogOut, AuditPage

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=AuditPage)
def list_audit_logs(
    _: AdminUser,
    db: Db,
    action: str | None = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> AuditPage:
    query = select(AuditLog)
    if action:
        prefixes = [p.strip() for p in action.split(",") if p.strip()]
        query = query.where(or_(*(AuditLog.action.startswith(p) for p in prefixes)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = (
        db.scalars(query.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)).unique().all()
    )
    return AuditPage(items=[AuditLogOut.model_validate(a) for a in items], total=total)
