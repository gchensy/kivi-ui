"""Vectorized rule evaluation over a DataFrame.

Backtests evaluate a whole dataset; the decision API evaluates a one-row
frame with the same code, so both paths share one semantics. Comparisons
with a missing value are false (``is_null`` is the way to test for it).
"""

import hashlib
import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..analytics.training import score_frame
from .dsl import MODEL_FIELD, SEVERITY, Condition, Definition, Group

Hasher = Callable[[str], str]


class RuleError(ValueError):
    def __init__(self, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.code, self.detail = code, detail


# ---- Watchlist values -----------------------------------------------------------------------


_SEPARATORS = re.compile(r"[\s\-]+")


def normalise_value(value: Any) -> str | None:
    """Canonical identifier text: integral floats lose ".0"; text is upper-cased without spaces or dashes.

    Identifiers are pasted as "138 0013 8000" or "138-0013-8000"; all spellings hash the same.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NA:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = _SEPARATORS.sub("", str(value)).upper()
    return text or None


def make_hasher(key: str) -> Hasher:
    secret = hashlib.sha256(f"kivi-list:{key}".encode()).digest()

    def digest(text: str) -> str:
        return hmac.new(secret, text.encode(), hashlib.sha256).hexdigest()

    return digest


def mask_text(text: str) -> str:
    """Keep enough to recognise a value without storing it: 138****1234."""
    n = len(text)
    if n >= 8:
        return text[:3] + "*" * (n - 7) + text[-4:]
    if n >= 4:
        return text[0] + "*" * (n - 2) + text[-1]
    return "*" * n


# ---- Context --------------------------------------------------------------------------------


@dataclass
class ModelRuntime:
    code: str
    version_id: str
    version: int
    result: dict[str, Any]


@dataclass
class Context:
    models: dict[str, ModelRuntime] = field(default_factory=dict)
    lists: dict[str, frozenset[str]] = field(default_factory=dict)
    hasher: Hasher | None = None


@dataclass
class Evaluation:
    hits: pd.DataFrame  # one boolean column per enabled rule
    decision: pd.Series
    deciding_rule: pd.Series  # code of the rule that set the decision, or ""
    outputs: pd.DataFrame  # model:CODE.score / .prob columns
    missing_fields: list[str]
    trace: list[dict[str, Any]] | None = None


def _model_outputs(frame: pd.DataFrame, codes: set[str], ctx: Context, missing: set[str]) -> pd.DataFrame:
    outputs = pd.DataFrame(index=frame.index)
    for code in sorted(codes):
        runtime = ctx.models.get(code)
        if runtime is None:
            raise RuleError("model_not_online", f"Model {code} has no online version", model=code)
        columns = {}
        for f in runtime.result["features"]:
            source = next(
                (c for c in (f["column"], f.get("header"), f["code"]) if c and c in frame.columns), None
            )
            if source is None:
                missing.add(f["code"])
                columns[f["column"]] = pd.Series(np.nan, index=frame.index)
            else:
                columns[f["column"]] = frame[source]
        scored = score_frame(runtime.result, pd.DataFrame(columns, index=frame.index))
        outputs[f"model:{code}.score"] = scored["score"]
        outputs[f"model:{code}.prob"] = scored["probability"]
    return outputs


def _series(frame: pd.DataFrame, outputs: pd.DataFrame, name: str, missing: set[str]) -> pd.Series:
    if name in outputs.columns:
        return outputs[name]
    if name in frame.columns:
        return frame[name]
    missing.add(name)
    return pd.Series([None] * len(frame), index=frame.index, dtype=object)


def _numbers(values: list[Any]) -> bool:
    return all(isinstance(v, int | float) and not isinstance(v, bool) for v in values)


def _condition(c: Condition, s: pd.Series, ctx: Context) -> pd.Series:
    present = s.notna() & ~(s.astype("string").str.strip() == "").fillna(False)
    op, value = c.op, c.value
    if op == "is_null":
        return ~present
    if op == "not_null":
        return present
    if op in ("gt", "ge", "lt", "le", "between"):
        x = pd.to_numeric(s, errors="coerce")
        if op == "between":
            out = (x >= value[0]) & (x <= value[1])
        else:
            out = {"gt": x > value, "ge": x >= value, "lt": x < value, "le": x <= value}[op]
        return out.fillna(False).astype(bool)
    if op in ("eq", "ne", "in", "not_in"):
        values = value if isinstance(value, list) else [value]
        if _numbers(values):
            x = pd.to_numeric(s, errors="coerce")
            member = x.isin([float(v) for v in values])
            known = x.notna()
        else:
            x = s.astype("string").str.strip()
            member = x.isin([str(v).strip() for v in values]).fillna(False)
            known = present
        out = member if op in ("eq", "in") else ~member
        return (out & known).astype(bool)
    if op in ("in_list", "not_in_list"):
        listed = ctx.lists.get(str(value))
        if listed is None:
            raise RuleError("list_not_found", f"Watchlist {value} does not exist", list=str(value))
        if ctx.hasher is None:
            raise RuleError("list_unavailable", "Watchlists need a hasher")
        digests = s.map(lambda v: ctx.hasher(t) if (t := normalise_value(v)) else None)
        member = digests.isin(listed)
        out = member if op == "in_list" else ~member
        return (out & digests.notna()).astype(bool)
    raise RuleError("bad_operator", f"Unknown operator {op}")


def _group(g: Group, frame, outputs, ctx, missing, trace_row: int | None, sensitive: frozenset[str]):
    masks, nodes = [], []
    for item in g.items:
        if isinstance(item, Group):
            mask, node = _group(item, frame, outputs, ctx, missing, trace_row, sensitive)
        else:
            s = _series(frame, outputs, item.field, missing)
            mask = _condition(item, s, ctx)
            node = None
            if trace_row is not None:
                actual = s.iloc[trace_row]
                if item.field in sensitive:
                    text = normalise_value(actual)
                    actual = mask_text(text) if text else None
                elif isinstance(actual, float) and np.isnan(actual):
                    actual = None
                elif hasattr(actual, "item"):
                    actual = actual.item()
                node = {
                    "field": item.field,
                    "op": item.op,
                    "value": item.value,
                    "actual": actual,
                    "result": bool(mask.iloc[trace_row]),
                }
        masks.append(mask)
        if node is not None:
            nodes.append(node)
    if not masks:
        combined = pd.Series(g.mode == "all", index=frame.index)
    elif g.mode == "all":
        combined = np.logical_and.reduce(masks)
    else:
        combined = np.logical_or.reduce(masks)
    combined = pd.Series(np.asarray(combined, dtype=bool), index=frame.index)
    node = None
    if trace_row is not None:
        node = {"mode": g.mode, "items": nodes, "result": bool(combined.iloc[trace_row])}
    return combined, node


def evaluate(definition: Definition, frame: pd.DataFrame, ctx: Context, *, trace: bool = False) -> Evaluation:
    """Evaluate every enabled rule on every row and combine them into decisions."""
    from .dsl import list_fields, references

    refs = references(definition)
    sensitive = frozenset(list_fields(definition))
    missing: set[str] = set()
    outputs = _model_outputs(frame, refs["models"], ctx, missing)
    rules = [r for r in definition.rules if r.enabled]
    hits = pd.DataFrame(index=frame.index)
    traces = [] if trace else None
    for rule in rules:
        mask, node = _group(rule.when, frame, outputs, ctx, missing, 0 if trace else None, sensitive)
        hits[rule.code] = mask
        if traces is not None:
            traces.append(
                {
                    "code": rule.code,
                    "name": rule.name,
                    "name_en": rule.name_en,
                    "decision": rule.decision,
                    "terminal": rule.terminal,
                    "hit": bool(mask.iloc[0]),
                    "when": node,
                }
            )

    n = len(frame)
    decision = np.full(n, definition.default_decision, dtype=object)
    deciding = np.full(n, "", dtype=object)
    best = np.full(n, -1)
    decided = np.zeros(n, dtype=bool)  # by a terminal rule
    for rule in rules:
        hit = hits[rule.code].to_numpy()
        if rule.terminal:
            take = hit & ~decided
            decision[take], deciding[take] = rule.decision, rule.code
            decided |= take
            continue
        level = SEVERITY[rule.decision]
        take = hit & ~decided & (level > best)
        decision[take], deciding[take] = rule.decision, rule.code
        best = np.where(take, level, best)
    return Evaluation(
        hits=hits,
        decision=pd.Series(decision, index=frame.index),
        deciding_rule=pd.Series(deciding, index=frame.index),
        outputs=outputs,
        missing_fields=sorted(f for f in missing if not MODEL_FIELD.match(f)),
        trace=traces,
    )


# ---- Backtest -------------------------------------------------------------------------------


def _rate(part: pd.Series) -> float | None:
    return round(float(part.mean()), 6) if len(part) else None


def summarise(
    definition: Definition, result: Evaluation, y: pd.Series | None, months: pd.Series | None
) -> dict[str, Any]:
    n = len(result.decision)
    counts = result.decision.value_counts()
    summary: dict[str, Any] = {"rows": n, "missing_fields": result.missing_fields}
    for d in ("pass", "review", "reject"):
        summary[d] = int(counts.get(d, 0))
        summary[f"{d}_rate"] = round(summary[d] / n, 6) if n else None
    if y is not None:
        summary["bad_rate"] = _rate(y)
        summary["bad_rate_by_decision"] = {
            d: _rate(y[result.decision == d]) for d in ("pass", "review", "reject")
        }
    blocking = [r.code for r in definition.rules if r.enabled and r.decision != "pass"]
    rules = []
    for rule in definition.rules:
        if not rule.enabled:
            rules.append(
                {
                    "code": rule.code,
                    "enabled": False,
                    "hits": 0,
                    "hit_rate": 0,
                    "exclusive": 0,
                    "decisive": 0,
                    "bad_rate": None,
                }
            )
            continue
        hit = result.hits[rule.code]
        others = result.hits[[c for c in blocking if c != rule.code]].any(axis=1) if blocking else False
        rules.append(
            {
                "code": rule.code,
                "enabled": True,
                "hits": int(hit.sum()),
                "hit_rate": _rate(hit),
                "exclusive": int((hit & ~others).sum()),
                "decisive": int((result.deciding_rule == rule.code).sum()),
                "bad_rate": _rate(y[hit]) if y is not None else None,
            }
        )
    summary["rules"] = rules
    if months is not None:
        monthly = []
        frame = pd.DataFrame({"month": months, "decision": result.decision})
        if y is not None:
            frame["y"] = y
        for month, part in frame.dropna(subset=["month"]).groupby("month", sort=True):
            entry = {
                "month": str(month),
                "rows": int(len(part)),
                "pass_rate": _rate(part.decision == "pass"),
                "reject_rate": _rate(part.decision == "reject"),
            }
            if y is not None:
                entry["pass_bad_rate"] = _rate(part.y[part.decision == "pass"])
            monthly.append(entry)
        summary["monthly"] = monthly
    return summary


def swap(a: pd.Series, b: pd.Series, y: pd.Series | None) -> list[dict[str, Any]]:
    """Decision of version A against version B for the same rows (swap-in / swap-out)."""
    cells = []
    for da in ("pass", "review", "reject"):
        for db in ("pass", "review", "reject"):
            mask = (a == da) & (b == db)
            cells.append(
                {
                    "from": da,
                    "to": db,
                    "rows": int(mask.sum()),
                    "bad_rate": _rate(y[mask]) if y is not None else None,
                }
            )
    return cells
