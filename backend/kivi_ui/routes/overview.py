"""The risk overview and the stability view, built from live data.

The overview reads decision logs (last 30 local days against the 30 before), the online
strategy with the most traffic and the model it scores with, and the alert centre. The
stability view stitches together the latest runs of one model's monitors.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, Db
from ..models import Alert, DecisionLog, ModelVersion, Monitor, RiskModel, Strategy, StrategyVersion
from ..monitor_schemas import AlertOut
from ..monitoring.checks import DEFAULT_THRESHOLDS
from ..monitoring.schedule import zone
from ..rules.dsl import Definition, references
from .monitors import alert_page, latest_runs, outs

router = APIRouter(tags=["overview"])
DECISIONS = ("pass", "review", "reject")
MODEL_KINDS = ("score_psi", "model_ks", "indicator_psi")


def _rate(part: int, total: int) -> float | None:
    return round(part / total, 6) if total else None


def _counts(db: Session, start: datetime, end: datetime, code: str | None = None) -> dict[str, Any]:
    query = select(DecisionLog.decision, func.count()).where(
        DecisionLog.created_at >= start, DecisionLog.created_at < end
    )
    if code:
        query = query.where(DecisionLog.strategy_code == code)
    found = dict(db.execute(query.group_by(DecisionLog.decision)).all())
    counts: dict[str, Any] = {d: int(found.get(d, 0)) for d in DECISIONS}
    counts["total"] = sum(counts[d] for d in DECISIONS)
    counts["approval_rate"] = _rate(counts["pass"], counts["total"])
    return counts


def _daily(db: Session, start: datetime, end: datetime, first: date, days: int) -> list[dict[str, Any]]:
    day = func.date(func.timezone(zone().key, DecisionLog.created_at))
    rows = db.execute(
        select(day, DecisionLog.decision, func.count())
        .where(DecisionLog.created_at >= start, DecisionLog.created_at < end)
        .group_by(day, DecisionLog.decision)
    ).all()
    found: dict[date, dict[str, int]] = {}
    for d, decision, n in rows:
        found.setdefault(d, {})[decision] = int(n)
    out = []
    for i in range(days):
        d = first + timedelta(days=i)
        c = {k: found.get(d, {}).get(k, 0) for k in DECISIONS}
        total = sum(c.values())
        out.append({"date": d.isoformat(), **c, "total": total, "approval_rate": _rate(c["pass"], total)})
    return out


def _rule_hits(
    db: Session, code: str, rules, start: datetime, end: datetime, total: int
) -> list[dict[str, Any]]:
    window = (
        DecisionLog.strategy_code == code,
        DecisionLog.created_at >= start,
        DecisionLog.created_at < end,
    )
    expanded = (
        select(func.jsonb_array_elements_text(DecisionLog.hit_rules).label("code")).where(*window).subquery()
    )
    hits = dict(db.execute(select(expanded.c.code, func.count()).group_by(expanded.c.code)).all())
    only = DecisionLog.hit_rules.op("->>")(0)
    exclusive = dict(
        db.execute(
            select(only, func.count())
            .where(*window, func.jsonb_array_length(DecisionLog.hit_rules) == 1)
            .group_by(only)
        ).all()
    )
    return [
        {
            "code": r.code,
            "label": {"zh": r.name, "en": r.name_en or r.name},
            "decision": r.decision,
            "hits": int(hits.get(r.code, 0)),
            "hit_rate": _rate(int(hits.get(r.code, 0)), total),
            "exclusive": int(exclusive.get(r.code, 0)),
        }
        for r in rules
    ]


def _online_model(db: Session, codes: set[str]) -> tuple[RiskModel, ModelVersion] | None:
    query = (
        select(RiskModel, ModelVersion)
        .join(ModelVersion, ModelVersion.model_id == RiskModel.id)
        .where(ModelVersion.status == "online")
    )
    rows = db.execute(query.order_by(ModelVersion.approved_at.desc().nulls_last())).unique().all()
    preferred = [r for r in rows if r[0].code in codes]
    return (preferred or rows or [None])[0]


def _model_block(model: RiskModel, version: ModelVersion) -> dict[str, Any]:
    focus = version.result.get("focus", "oot")
    return {
        "id": str(model.id),
        "code": model.code,
        "name": {"zh": model.name, "en": model.name_en or model.name},
        "version": version.version,
        "version_id": str(version.id),
        "focus": focus,
        "auc_train": version.auc_train,
        "ks_train": version.ks_train,
        "auc_focus": getattr(version, f"auc_{focus}", None),
        "ks_focus": getattr(version, f"ks_{focus}", None),
    }


def _score_psi(db: Session, model_id: uuid.UUID) -> dict[str, Any] | None:
    monitors = (
        db.scalars(
            select(Monitor)
            .where(Monitor.model_id == model_id, Monitor.kind == "score_psi")
            .order_by(Monitor.created_at)
        )
        .unique()
        .all()
    )
    runs = latest_runs(db, [m.id for m in monitors])
    for m in monitors:
        run = runs.get(m.id)
        if run is not None:
            return {
                "monitor_id": str(m.id),
                "value": run.value,
                "level": run.level,
                "period": run.detail.get("period"),
                "thresholds": m.thresholds,
                "ran_at": run.created_at.isoformat(),
            }
    return None


@router.get("/overview")
def overview(_: CurrentUser, db: Db) -> dict[str, Any]:
    tz = zone()
    now = datetime.now(UTC)
    today = now.astimezone(tz).date()
    first = today - timedelta(days=29)
    start = datetime.combine(first, time(), tz).astimezone(UTC)
    prev_start = start - timedelta(days=30)
    current, previous = _counts(db, start, now), _counts(db, prev_start, start)
    sources = dict(
        db.execute(
            select(DecisionLog.source, func.count())
            .where(DecisionLog.created_at >= start, DecisionLog.created_at < now)
            .group_by(DecisionLog.source)
        ).all()
    )

    # The online strategy with the most decisions in the window.
    online = (
        db.execute(
            select(Strategy, StrategyVersion)
            .join(StrategyVersion, StrategyVersion.strategy_id == Strategy.id)
            .where(StrategyVersion.status == "online")
        )
        .unique()
        .all()
    )
    volume = dict(
        db.execute(
            select(DecisionLog.strategy_code, func.count())
            .where(DecisionLog.created_at >= start, DecisionLog.created_at < now)
            .group_by(DecisionLog.strategy_code)
        ).all()
    )
    strategy_block, model_codes = None, set()
    if online:
        strategy, version = max(online, key=lambda sv: (volume.get(sv[0].code, 0), sv[0].code))
        definition = Definition.model_validate(version.definition)
        model_codes = references(definition)["models"]
        counts = _counts(db, start, now, strategy.code)
        summary = (version.backtest or {}).get("summary") or {}
        strategy_block = {
            "id": str(strategy.id),
            "code": strategy.code,
            "name": {"zh": strategy.name, "en": strategy.name_en or strategy.name},
            "version": version.version,
            "version_id": str(version.id),
            "decisions": counts,
            "rules": _rule_hits(
                db, strategy.code, [r for r in definition.rules if r.enabled], start, now, counts["total"]
            ),
            "effect": summary.get("bad_rate_by_decision"),
            "effect_dataset": ((version.backtest or {}).get("dataset") or {}).get("name"),
        }

    found = _online_model(db, model_codes)
    model_block = _model_block(*found) if found else None
    score_psi = _score_psi(db, found[0].id) if found else None
    alerts = alert_page(db, "active", size=5)
    monitors = outs(
        db, list(db.scalars(select(Monitor).where(Monitor.enabled).order_by(Monitor.created_at)).unique())
    )
    return {
        "as_of": today.isoformat(),
        "generated_at": now.isoformat(timespec="seconds"),
        "timezone": tz.key,
        "decisions": {
            "current": current,
            "previous": previous,
            "daily": _daily(db, start, now, first, 30),
            "sources": {k: int(v) for k, v in sources.items()},
        },
        "strategy": strategy_block,
        "model": model_block,
        "score_psi": score_psi,
        "alerts": {"counts": alerts.counts, "items": [a.model_dump(mode="json") for a in alerts.items]},
        "monitors": [m.model_dump(mode="json") for m in monitors],
    }


@router.get("/stability")
def stability(_: CurrentUser, db: Db, model_id: uuid.UUID | None = None) -> dict[str, Any]:
    monitors = (
        db.scalars(
            select(Monitor)
            .where(Monitor.model_id.isnot(None), Monitor.kind.in_(MODEL_KINDS))
            .order_by(Monitor.enabled.desc(), Monitor.created_at)
        )
        .unique()
        .all()
    )
    models: dict[uuid.UUID, RiskModel] = {}
    for m in monitors:
        models.setdefault(m.model_id, m.model)
    options = [
        {"id": str(m.id), "code": m.code, "name": {"zh": m.name, "en": m.name_en or m.name}}
        for m in models.values()
    ]
    if not models:
        return {"models": [], "model": None}
    chosen = models.get(model_id) if model_id else None
    if chosen is None:
        found = _online_model(db, {m.code for m in models.values()})
        chosen = found[0] if found and found[0].id in models else next(iter(models.values()))
    by_kind: dict[str, Monitor] = {}
    for m in monitors:
        if m.model_id == chosen.id:
            by_kind.setdefault(m.kind, m)
    runs = latest_runs(db, [m.id for m in by_kind.values()])
    run_of = {kind: runs.get(m.id) for kind, m in by_kind.items()}

    def series(kind: str) -> dict[str, dict[str, Any]]:
        run = run_of.get(kind)
        return {s["period"]: s for s in (run.detail.get("series", []) if run else [])}

    score, ks, indicators = series("score_psi"), series("model_ks"), series("indicator_psi")
    months = sorted(set(score) | set(ks) | set(indicators))
    monthly = []
    for month in months:
        s, k, i = score.get(month, {}), ks.get(month, {}), indicators.get(month, {})
        base = s or k or i
        monthly.append(
            {
                "month": month,
                "score_psi": s.get("value"),
                "auc": k.get("auc"),
                "ks": k.get("ks"),
                "rows": base.get("rows"),
                "bad_rate": s.get("bad_rate", k.get("bad_rate")),
                "in_reference": bool(base.get("in_reference")),
            }
        )
    feature_psi = []
    ind_run = run_of.get("indicator_psi")
    if ind_run is not None:
        own = list(ind_run.detail.get("series", []))
        position = {s["period"]: n for n, s in enumerate(own)}
        for row in ind_run.detail.get("indicators", []):
            feature_psi.append(
                {
                    "name": row["code"],
                    "label": {"zh": row["name"], "en": row.get("name_en") or row["name"]},
                    "values": [row["values"][position[m]] if m in position else None for m in months],
                }
            )
    ids = [m.id for m in by_kind.values()]
    alerts = (
        db.scalars(
            select(Alert)
            .where(Alert.monitor_id.in_(ids), Alert.status != "resolved")
            .order_by(Alert.last_seen_at.desc())
        )
        .unique()
        .all()
        if ids
        else []
    )
    score_monitor = by_kind.get("score_psi") or by_kind.get("indicator_psi")
    reference_run = run_of.get("score_psi") or run_of.get("model_ks") or run_of.get("indicator_psi")
    return {
        "models": options,
        "model": {
            "id": str(chosen.id),
            "code": chosen.code,
            "name": {"zh": chosen.name, "en": chosen.name_en or chosen.name},
        },
        "thresholds": score_monitor.thresholds if score_monitor else DEFAULT_THRESHOLDS["score_psi"],
        "ks_thresholds": by_kind["model_ks"].thresholds
        if "model_ks" in by_kind
        else DEFAULT_THRESHOLDS["model_ks"],
        "reference": reference_run.detail.get("reference") if reference_run else None,
        "reference_metrics": run_of["model_ks"].detail.get("reference_metrics")
        if run_of.get("model_ks")
        else None,
        "months": months,
        "monthly": monthly,
        "feature_psi": feature_psi,
        "monitors": {
            kind: {
                "id": str(m.id),
                "name": m.name,
                "level": m.last_level,
                "value": m.last_value,
                "ran_at": run_of[kind].created_at.isoformat() if run_of.get(kind) else None,
            }
            for kind, m in by_kind.items()
        },
        "alerts": [AlertOut.model_validate(a).model_dump(mode="json") for a in alerts],
    }
