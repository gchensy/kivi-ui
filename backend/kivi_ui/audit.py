"""Audit trail helper. Callers commit the session."""

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog, User


def client_ip(request: Request | None) -> str | None:
    return request.client.host if request and request.client else None


def record(
    db: Session,
    action: str,
    *,
    actor: User | None,
    request: Request | None = None,
    entity_type: str | None = None,
    entity_id: object | None = None,
    **detail: Any,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail,
            ip=client_ip(request),
        )
    )
