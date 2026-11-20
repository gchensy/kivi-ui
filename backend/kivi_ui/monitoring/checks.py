"""The checks a monitor can run. Each returns a headline value and the detail behind it.

Dataset checks (``indicator_psi``, ``score_psi``, ``model_ks``) split a dated sample by month
and compare every month with a reference period: by default the model's training months when
the sample is its training dataset, otherwise the first half of the months. The headline is the
latest month. Strategy checks (``approval_rate``, ``rule_hit_rate``) compare the last days of
decision logs with the days before them.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics import binning, metrics
from ..analytics.training import score_frame
from ..data import store
from ..models import Dataset, DecisionLog, Indicator, ModelVersion, Monitor, StrategyVersion
from ..rules.dsl import Definition
from .schedule import zone

KINDS = ("indicator_psi", "score_psi", "model_ks", "approval_rate", "rule_hit_rate")
TARGET = {
    "indicator_psi": "model_or_indicators",
    "score_psi": "model",
    "model_ks": "model",
    "approval_rate": "strategy",
    "rule_hit_rate": "strategy",
}
DEFAULT_THRESHOLDS = {
    "indicator_psi": {"warn": 0.10, "alert": 0.25},
    "score_psi": {"warn": 0.10, "alert": 0.25},
    "model_ks": {"warn": 0.10, "alert": 0.20},  # relative KS drop against the reference period
    "approval_rate": {"warn": 0.05, "alert": 0.10},  # absolute change, either direction
    "rule_hit_rate": {"warn": 0.05, "alert": 0.10},
}
SHIFT_KINDS = {"approval_rate", "rule_hit_rate"}


class CheckError(Exception):
    """A check that cannot run with its current configuration or data."""

    def __init__(self, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.code, self.detail = code, detail


@dataclass
class Outcome:
    value: float | None
    detail: dict[str, Any] = field(default_factory=dict)


def level_of(kind: str, value: float | None, thresholds: dict[str, float]) -> str:
    if value is None:
        return "normal"
    v = abs(value) if kind in SHIFT_KINDS else value
    return "alert" if v >= thresholds["alert"] else "warn" if v >= thresholds["warn"] else "normal"


def _r(value: float | None, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


# ---- Dated samples -------------------------------------------------------------------------


def resolve(dataset: Dataset, *names: str | None) -> str | None:
    """The SQL column of `dataset` matching the first name given (column name, header or code).

    Give the uploaded header first: SQL names of non-ASCII headers are positional (``c8``), so in
    another sample the same SQL name can be a different column.
    """
    for name in names:
        if not name:
            continue
        for c in dataset.columns:
            if name in (c.column_name, c.name):
                return c.column_name
    return None


def _dated(db: Session, dataset: Dataset | None, columns: list[str], labels: bool = False):
    if dataset is None:
        raise CheckError("dataset_required", "Choose a dataset for this monitor")
    if not dataset.date_column:
        raise CheckError("no_date_column", "Set the date column of the dataset first", dataset=dataset.name)
    if labels and not dataset.target_column:
        raise CheckError("no_target", "Set the target column of the dataset first", dataset=dataset.name)
    wanted = [*columns, dataset.date_column] + ([dataset.target_column] if dataset.target_column else [])
    frame = store.read_columns(db, dataset, list(dict.fromkeys(wanted)))
    month = pd.to_datetime(frame[dataset.date_column], errors="coerce").dt.to_period("M").astype("string")
    frame = frame.assign(_month=month).dropna(subset=["_month"]).reset_index(drop=True)
    months = sorted(frame["_month"].unique())
    if len(months) < 2:
        raise CheckError("too_few_months", "The dataset covers fewer than two months", dataset=dataset.name)
    y = store.labels(dataset, frame) if dataset.target_column else pd.Series(float("nan"), index=frame.index)
    return frame, months, y


def _reference(months: list[str], params: dict[str, Any], default: list[str] | None) -> list[str]:
    ref = params.get("reference") or {}
    first_half = months[: max(1, len(months) // 2)]
    if ref.get("start") and ref.get("end"):
        start, end = ref["start"], ref["end"]
    elif default:
        start, end = default
        # A model trained on every month (no out-of-time months) leaves nothing to compare.
        if not [m for m in months if m > end]:
            return first_half
    else:
        return first_half
    chosen = [m for m in months if start <= m <= end]
    if not chosen:
        raise CheckError("bad_reference", "No data in the reference period", start=start, end=end)
    if chosen[-1] == months[-1]:
        raise CheckError("bad_reference", "The reference period must end before the latest month")
    return chosen


def online_version(db: Session, monitor: Monitor) -> ModelVersion:
    version = db.scalar(
        select(ModelVersion).where(ModelVersion.model_id == monitor.model_id, ModelVersion.status == "online")
    )
    if version is None:
        raise CheckError("model_not_online", "The model has no online version", model=monitor.model.code)
    return version


def _model_inputs(dataset: Dataset, result: dict[str, Any]) -> dict[str, str]:
    columns, missing = {}, []
    for f in result["features"]:
        source = resolve(dataset, f.get("header"), f["column"], f["code"])
        if source is None:
            missing.append(f["code"])
        columns[f["column"]] = source
    if missing:
        raise CheckError("missing_columns", "The dataset lacks model inputs", columns=missing)
    return columns


def _scored(db: Session, monitor: Monitor, labels: bool = False):
    version = online_version(db, monitor)
    dataset = monitor.dataset
    if dataset is None:
        raise CheckError("dataset_required", "Choose a dataset for this monitor")
    inputs = _model_inputs(dataset, version.result)
    frame, months, y = _dated(db, dataset, list(inputs.values()), labels=labels)
    x = pd.DataFrame({column: frame[source] for column, source in inputs.items()})
    scored = score_frame(version.result, x)
    trained = version.result.get("evaluation", {}).get("train", {}).get("period")
    default = trained if version.dataset_id == dataset.id else None
    reference = _reference(months, monitor.params, default)
    model = {"code": monitor.model.code, "version": version.version, "version_id": str(version.id)}
    return frame, months, y, scored, reference, model, version


def score_psi(db: Session, monitor: Monitor) -> Outcome:
    frame, months, y, scored, reference, model, version = _scored(db, monitor)
    bands = metrics.band_codes(scored["score"], version.result["band_cuts"])
    in_ref = frame["_month"].isin(reference)
    series = []
    for m in months:
        part = frame["_month"] == m
        labelled = y[part].dropna()
        series.append(
            {
                "period": m,
                "rows": int(part.sum()),
                "value": _r(metrics.psi(bands[in_ref], bands[part])),
                "mean_score": _r(scored["score"][part].mean(), 1),
                "bad_rate": _r(labelled.mean()) if len(labelled) else None,
                "in_reference": m in reference,
            }
        )
    return Outcome(
        series[-1]["value"],
        {"model": model, "reference": [reference[0], reference[-1]], "period": months[-1], "series": series},
    )


def model_ks(db: Session, monitor: Monitor) -> Outcome:
    frame, months, y, scored, reference, model, _ = _scored(db, monitor, labels=True)
    probability = scored["probability"]

    def discrimination(mask: pd.Series) -> dict[str, Any]:
        labelled = mask & y.notna()
        if y[labelled].nunique() < 2:
            return {"auc": None, "ks": None, "labelled": int(labelled.sum())}
        r = metrics.roc(y[labelled], probability[labelled].to_numpy())
        return {"auc": r["auc"], "ks": r["ks"], "labelled": int(labelled.sum())}

    base = discrimination(frame["_month"].isin(reference))
    if not base["ks"]:
        raise CheckError("no_labels", "The reference period has no usable labels")
    series = []
    for m in months:
        part = frame["_month"] == m
        d = discrimination(part)
        labelled = y[part].dropna()
        series.append(
            {
                "period": m,
                "rows": int(part.sum()),
                "value": d["ks"],
                "auc": d["auc"],
                "ks": d["ks"],
                "labelled": d["labelled"],
                "bad_rate": _r(labelled.mean()) if len(labelled) else None,
                "in_reference": m in reference,
            }
        )
    current = [s for s in series if not s["in_reference"] and s["ks"] is not None]
    if not current:
        raise CheckError("no_labelled_months", "No labelled month after the reference period")
    latest = current[-1]
    return Outcome(
        _r(1 - latest["ks"] / base["ks"]),
        {
            "model": model,
            "reference": [reference[0], reference[-1]],
            "reference_metrics": base,
            "period": latest["period"],
            "auc": latest["auc"],
            "ks": latest["ks"],
            "series": series,
        },
    )


def indicator_psi(db: Session, monitor: Monitor) -> Outcome:
    dataset = monitor.dataset
    if dataset is None:
        raise CheckError("dataset_required", "Choose a dataset for this monitor")
    targets, skipped, default = [], [], None
    ids = monitor.params.get("indicator_ids") or []
    if monitor.model_id and not ids:
        version = online_version(db, monitor)
        trained = version.result.get("evaluation", {}).get("train", {}).get("period")
        default = trained if version.dataset_id == dataset.id else None
        for f in version.result["features"]:
            column = resolve(dataset, f.get("header"), f["column"], f["code"])
            item = {"code": f["code"], "name": f["name"], "name_en": f.get("name_en")}
            if column is None:
                skipped.append({**item, "reason": "missing_column"})
            else:
                targets.append((item, column, binning.Rule.from_dict(f["rule"])))
    else:
        indicators = db.scalars(select(Indicator).where(Indicator.id.in_(ids))).unique().all()
        for ind in sorted(indicators, key=lambda i: i.code):
            item = {"code": ind.code, "name": ind.name, "name_en": ind.name_en}
            source = ind.dataset.columns if ind.dataset else []
            header = next((c.name for c in source if c.column_name == ind.column_name), None)
            column = resolve(dataset, header, ind.column_name, ind.code)
            if column is None:
                skipped.append({**item, "reason": "missing_column"})
            elif ind.default_scheme is None:
                skipped.append({**item, "reason": "no_scheme"})
            else:
                targets.append((item, column, binning.Rule.from_dict(ind.default_scheme.rule)))
    if not targets:
        raise CheckError(
            "no_indicators", "None of the indicators can be checked on this dataset", skipped=skipped
        )
    frame, months, _ = _dated(db, dataset, [column for _, column, _ in targets])
    reference = _reference(months, monitor.params, default)
    in_ref = frame["_month"].isin(reference)
    parts = {m: frame["_month"] == m for m in months}
    rows = []
    for item, column, rule in targets:
        groups = rule.assign(frame[column])
        values = [_r(binning.psi_table_value(groups[in_ref], groups[parts[m]])) for m in months]
        rows.append({**item, "values": values, "latest": values[-1]})
    rows.sort(key=lambda r: -(r["latest"] or 0))
    worst = rows[0]
    series = [
        {
            "period": m,
            "rows": int(parts[m].sum()),
            "value": _r(max((r["values"][i] or 0) for r in rows)),
            "in_reference": m in reference,
        }
        for i, m in enumerate(months)
    ]
    return Outcome(
        worst["latest"],
        {
            "reference": [reference[0], reference[-1]],
            "period": months[-1],
            "indicators": rows,
            "worst": {k: worst[k] for k in ("code", "name", "name_en")} | {"value": worst["latest"]},
            "skipped": skipped,
            "series": series,
        },
    )


# ---- Decision logs ---------------------------------------------------------------------------


def _windows(monitor: Monitor, now: datetime):
    window = int(monitor.params.get("window_days", 7))
    baseline = int(monitor.params.get("baseline_days", 30))
    current_start = now - timedelta(days=window)
    return window, baseline, current_start, current_start - timedelta(days=baseline)


def _local_period(start: datetime, end: datetime) -> str:
    """The window as local dates, matching the daily series."""
    tz = zone()
    return f"{start.astimezone(tz).date().isoformat()}/{end.astimezone(tz).date().isoformat()}"


def _counts(db: Session, code: str, start: datetime, end: datetime) -> dict[str, int]:
    rows = db.execute(
        select(DecisionLog.decision, func.count())
        .where(
            DecisionLog.strategy_code == code, DecisionLog.created_at >= start, DecisionLog.created_at < end
        )
        .group_by(DecisionLog.decision)
    ).all()
    counts = {"pass": 0, "review": 0, "reject": 0} | {d: int(n) for d, n in rows}
    counts["total"] = sum(counts[d] for d in ("pass", "review", "reject"))
    return counts


def _enough(monitor: Monitor, current: dict, baseline: dict) -> None:
    need = int(monitor.params.get("min_requests", 30))
    if current["total"] < need or baseline["total"] < need:
        raise CheckError(
            "too_few_requests",
            "Too few decisions to compare",
            current=current["total"],
            baseline=baseline["total"],
            minimum=need,
        )


def approval_rate(db: Session, monitor: Monitor, now: datetime | None = None) -> Outcome:
    now = now or datetime.now(UTC)
    code = monitor.strategy.code
    window, baseline_days, current_start, baseline_start = _windows(monitor, now)
    current = _counts(db, code, current_start, now)
    baseline = _counts(db, code, baseline_start, current_start)
    _enough(monitor, current, baseline)
    for c in (current, baseline):
        c["rate"] = _r(c["pass"] / c["total"])
    tz = zone().key
    day = func.date(func.timezone(tz, DecisionLog.created_at))
    rows = db.execute(
        select(day, DecisionLog.decision, func.count())
        .where(
            DecisionLog.strategy_code == code,
            DecisionLog.created_at >= baseline_start,
            DecisionLog.created_at < now,
        )
        .group_by(day, DecisionLog.decision)
    ).all()
    days: dict[str, dict[str, int]] = {}
    for d, decision, n in rows:
        days.setdefault(d.isoformat(), {"pass": 0, "review": 0, "reject": 0})[decision] = int(n)
    current_day = current_start.astimezone(zone()).date().isoformat()
    series = []
    for d in sorted(days):
        c = days[d]
        total = c["pass"] + c["review"] + c["reject"]
        series.append(
            {
                "period": d,
                "rows": total,
                "value": _r(c["pass"] / total) if total else None,
                **c,
                "in_reference": d < current_day,
            }
        )
    return Outcome(
        _r(current["rate"] - baseline["rate"]),
        {
            "strategy": {"code": code},
            "window_days": window,
            "baseline_days": baseline_days,
            "current": current,
            "baseline": baseline,
            "period": _local_period(current_start, now),
            "series": series,
        },
    )


def rule_hit_rate(db: Session, monitor: Monitor, now: datetime | None = None) -> Outcome:
    now = now or datetime.now(UTC)
    code = monitor.strategy.code
    version = db.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == monitor.strategy_id, StrategyVersion.status == "online"
        )
    )
    if version is None:
        raise CheckError("strategy_not_online", "The strategy has no online version", strategy=code)
    rules = [r for r in Definition.model_validate(version.definition).rules if r.enabled]
    window, baseline_days, current_start, baseline_start = _windows(monitor, now)
    current, baseline = (
        _counts(db, code, current_start, now),
        _counts(db, code, baseline_start, current_start),
    )
    _enough(monitor, current, baseline)

    def hits(start: datetime, end: datetime) -> dict[str, int]:
        expanded = (
            select(func.jsonb_array_elements_text(DecisionLog.hit_rules).label("code"))
            .where(
                DecisionLog.strategy_code == code,
                DecisionLog.created_at >= start,
                DecisionLog.created_at < end,
            )
            .subquery()
        )
        rows = db.execute(select(expanded.c.code, func.count()).group_by(expanded.c.code)).all()
        return {c: int(n) for c, n in rows}

    now_hits, base_hits = hits(current_start, now), hits(baseline_start, current_start)
    rows = []
    for rule in rules:
        cur = now_hits.get(rule.code, 0) / current["total"]
        base = base_hits.get(rule.code, 0) / baseline["total"]
        rows.append(
            {
                "code": rule.code,
                "name": rule.name,
                "name_en": rule.name_en,
                "decision": rule.decision,
                "current": _r(cur),
                "baseline": _r(base),
                "shift": _r(cur - base),
            }
        )
    if not rows:
        raise CheckError("empty_strategy", "The online version has no enabled rules")
    worst = max(rows, key=lambda r: abs(r["shift"] or 0))
    return Outcome(
        worst["shift"],
        {
            "strategy": {"code": code, "version": version.version},
            "window_days": window,
            "baseline_days": baseline_days,
            "current_total": current["total"],
            "baseline_total": baseline["total"],
            "period": _local_period(current_start, now),
            "rules": rows,
            "worst": {k: worst[k] for k in ("code", "name", "name_en", "decision")}
            | {"value": worst["shift"]},
        },
    )


CHECKS = {
    "indicator_psi": indicator_psi,
    "score_psi": score_psi,
    "model_ks": model_ks,
    "approval_rate": approval_rate,
    "rule_hit_rate": rule_hit_rate,
}
