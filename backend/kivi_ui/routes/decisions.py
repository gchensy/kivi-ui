"""The real-time decision API (bearer tokens), the decision log and token management."""

import hashlib
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from fastapi import APIRouter, Header, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .. import audit
from ..deps import AdminUser, CurrentUser, Db
from ..errors import ApiError
from ..models import ApiToken, DecisionLog
from ..rules import runtime
from ..rules.dsl import list_fields
from ..rules.engine import RuleError, evaluate, mask_text, normalise_value
from ..strategy_schemas import (
    DecideIn,
    DecideOut,
    DecisionDetail,
    DecisionOut,
    DecisionPage,
    TokenCreated,
    TokenCreateIn,
    TokenOut,
)
from .strategies import response_body

router = APIRouter(tags=["decisions"])


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(db: Db, authorization: str | None) -> ApiToken:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "token_required", "Send an API token as 'Authorization: Bearer <token>'")
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == _digest(authorization[7:].strip())))
    now = datetime.now(UTC)
    if token is None or token.revoked_at is not None or (token.expires_at and token.expires_at <= now):
        raise ApiError(401, "invalid_token", "The API token is invalid, revoked or expired")
    if token.last_used_at is None or now - token.last_used_at > timedelta(minutes=1):
        token.last_used_at = now
    return token


def masked_input(definition, data: dict[str, Any]) -> dict[str, Any]:
    """Watchlist fields are identifiers: store them masked, never in full."""
    sensitive = list_fields(definition)
    out = {}
    for key, value in data.items():
        if key in sensitive and (text := normalise_value(value)):
            out[key] = mask_text(text)
        elif isinstance(value, str | int | float | bool) or value is None:
            out[key] = value
        else:
            out[key] = str(value)[:200]
    return out


def replay(log: DecisionLog) -> dict[str, Any]:
    hits = {t["code"]: t for t in log.trace}
    return {
        "request_id": log.request_id,
        "decision": log.decision,
        "reason": log.reason,
        "rules": [
            {
                "code": c,
                "name": hits.get(c, {}).get("name", c),
                "name_en": hits.get(c, {}).get("name_en"),
                "decision": hits.get(c, {}).get("decision", log.decision),
            }
            for c in log.hit_rules
        ],
        "scores": log.scores,
        "strategy": {"code": log.strategy_code, "version": log.version},
        "missing_fields": [],
        "latency_ms": log.latency_ms,
        "replayed": True,
    }


def _previous(db: Db, request_id: str, code: str) -> DecisionLog | None:
    """The stored decision for a repeated request_id; reusing one for another strategy is a conflict."""
    previous = db.scalar(select(DecisionLog).where(DecisionLog.request_id == request_id))
    if previous is not None and previous.strategy_code != code.upper():
        raise ApiError(
            409,
            "request_id_conflict",
            "This request_id was already used for another strategy",
            {"strategy": previous.strategy_code},
        )
    return previous


@router.post("/decide/{code}", response_model=DecideOut)
def decide(code: str, body: DecideIn, db: Db, authorization: str | None = Header(None)) -> dict[str, Any]:
    started = time.perf_counter()
    token = authenticate(db, authorization)
    if body.request_id and (previous := _previous(db, body.request_id, code)) is not None:
        db.commit()
        return replay(previous)
    loaded = runtime.online_strategy(db, code.upper())
    if loaded is None:
        raise ApiError(404, "strategy_not_online", "No online version of this strategy")
    strategy_id, version_id, number, definition, ctx = loaded
    try:
        result = evaluate(definition, pd.DataFrame([body.data]), ctx, trace=True)
    except RuleError as error:
        raise ApiError(422, error.code, str(error), error.detail) from error
    request_id = body.request_id or f"d-{uuid.uuid4().hex[:20]}"
    latency = (time.perf_counter() - started) * 1000
    out = response_body(definition, result, request_id, {"code": code.upper(), "version": number}, latency)
    db.add(
        DecisionLog(
            request_id=request_id,
            strategy_id=strategy_id,
            version_id=version_id,
            strategy_code=code.upper(),
            version=number,
            decision=out["decision"],
            reason=out["reason"],
            hit_rules=[r["code"] for r in out["rules"]],
            scores=out["scores"],
            trace=result.trace or [],
            input=masked_input(definition, body.data),
            latency_ms=out["latency_ms"],
            source="api",
            token_id=token.id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request with the same request_id was logged first: answer as a replay.
        db.rollback()
        previous = _previous(db, request_id, code)
        if previous is None:
            raise
        return replay(previous)
    return out


@router.get("/decisions", response_model=DecisionPage)
def list_decisions(
    _: CurrentUser,
    db: Db,
    strategy: str | None = Query(None, max_length=64),
    decision: str | None = Query(None, pattern="^(pass|review|reject)$"),
    rule: str | None = Query(None, max_length=32),
    source: str | None = Query(None, max_length=16),
    q: str | None = Query(None, max_length=64),
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> DecisionPage:
    query = select(DecisionLog)
    if strategy:
        query = query.where(DecisionLog.strategy_code == strategy.upper())
    if rule:
        query = query.where(DecisionLog.hit_rules.contains([rule]))
    if source:
        query = query.where(DecisionLog.source == source)
    if q:
        query = query.where(DecisionLog.request_id.startswith(q.strip()))
    if since:
        query = query.where(DecisionLog.created_at >= since)
    if until:
        query = query.where(DecisionLog.created_at < until)
    sub = query.subquery()
    counts = {d: 0 for d in ("pass", "review", "reject")}
    counts.update(dict(db.execute(select(sub.c.decision, func.count()).group_by(sub.c.decision)).all()))
    if decision:
        query = query.where(DecisionLog.decision == decision)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(DecisionLog.created_at.desc(), DecisionLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return DecisionPage(items=[DecisionOut.model_validate(i) for i in items], total=total, counts=counts)


@router.get("/decisions/{request_id}", response_model=DecisionDetail)
def get_decision(request_id: str, _: CurrentUser, db: Db) -> DecisionLog:
    log = db.scalar(select(DecisionLog).where(DecisionLog.request_id == request_id))
    if log is None:
        raise ApiError(404, "decision_not_found", "Decision not found")
    return log


# ---- API tokens (administrators) -----------------------------------------------------------


@router.get("/api-tokens", response_model=list[TokenOut])
def list_tokens(_: AdminUser, db: Db) -> list[ApiToken]:
    return list(db.scalars(select(ApiToken).order_by(ApiToken.created_at.desc())).unique())


@router.post("/api-tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(body: TokenCreateIn, request: Request, admin: AdminUser, db: Db) -> TokenCreated:
    plain = f"kv_{secrets.token_urlsafe(32)}"
    token = ApiToken(
        name=body.name.strip(),
        prefix=plain[:10],
        token_hash=_digest(plain),
        owner_id=admin.id,
        expires_at=datetime.now(UTC) + timedelta(days=body.expires_days) if body.expires_days else None,
    )
    db.add(token)
    db.flush()
    audit.record(
        db,
        "token.created",
        actor=admin,
        request=request,
        entity_type="token",
        entity_id=token.id,
        name=token.name,
    )
    db.commit()
    db.refresh(token)
    return TokenCreated(**TokenOut.model_validate(token).model_dump(), token=plain)


@router.delete("/api-tokens/{token_id}", response_model=TokenOut)
def revoke_token(token_id: uuid.UUID, request: Request, admin: AdminUser, db: Db) -> ApiToken:
    token = db.get(ApiToken, token_id)
    if token is None:
        raise ApiError(404, "token_not_found", "API token not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        audit.record(
            db,
            "token.revoked",
            actor=admin,
            request=request,
            entity_type="token",
            entity_id=token.id,
            name=token.name,
        )
        db.commit()
        db.refresh(token)
    return token
