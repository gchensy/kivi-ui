"""One binning interface over kivi's edge-fitting functions.

``fit`` turns a feature, its binary target and a :class:`BinSpec` into a frozen
:class:`Rule`; ``Rule.assign`` maps any sample to stable group codes, so the
same rule bins the reference data, later months and other datasets. Groups are
coded ``b<i>`` for intervals, ``s<i>`` for special values, ``c:<level>`` for
categories, ``other`` for merged rare levels and ``missing``.
"""

import math
import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from kivi.binning import bin_edges, chimerge_edges, cut, monotonic_edges, tree_edges
from kivi.evaluate import psi_table
from kivi.woe import woe_table
from pydantic import BaseModel, Field, model_validator

Method = Literal["quantile", "uniform", "chimerge", "tree", "monotonic", "manual", "category"]
NUMERIC_METHODS = ("quantile", "uniform", "chimerge", "tree", "monotonic", "manual")
SUPERVISED = ("chimerge", "tree", "monotonic")
MAX_CATEGORIES = 60


class BinningError(ValueError):
    """A spec that cannot be applied to the data (reported to the user)."""

    def __init__(self, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.code, self.detail = code, detail


class BinSpec(BaseModel):
    method: Method = "quantile"
    bins: int = Field(5, ge=2, le=20, description="Requested or maximum number of bins")
    cuts: list[float] = Field(default_factory=list, description="Interior cut points for manual")
    special: list[float] = Field(default_factory=list, description="Codes that each form their own bin")
    min_bin_share: float = Field(0.05, ge=0, le=0.5, description="Tree leaf share; rare category share")
    direction: Literal["auto", "increasing", "decreasing"] = "auto"
    alpha: float | None = Field(0.05, gt=0, lt=1)

    @model_validator(mode="after")
    def _manual_cuts(self) -> "BinSpec":
        finite = sorted({float(c) for c in self.cuts if math.isfinite(c)})
        if self.method == "manual" and not finite:
            raise ValueError("manual binning needs at least one cut point")
        self.cuts = finite
        self.special = sorted({float(v) for v in self.special if math.isfinite(v)})
        return self


@dataclass
class Rule:
    kind: Literal["numeric", "category"]
    cuts: list[float] = field(default_factory=list)
    special: list[float] = field(default_factory=list)
    levels: dict[str, str] = field(default_factory=dict)  # category level -> group code

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "cuts": self.cuts, "special": self.special, "levels": self.levels}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            data["kind"],
            list(data.get("cuts", [])),
            list(data.get("special", [])),
            dict(data.get("levels", {})),
        )

    def assign(self, values: pd.Series) -> pd.Series:
        if self.kind == "category":
            text = values.astype("string")
            groups = text.map(lambda v: self.levels.get(v, "other") if v is not pd.NA else "missing")
            return groups.fillna("missing").astype(str)
        numbers = pd.to_numeric(values, errors="coerce")
        edges = [-np.inf, *self.cuts, np.inf]
        grouped = cut(numbers, edges, special=self.special or None)
        codes = np.asarray(pd.Series(grouped).cat.codes)
        n_special = len(self.special)
        labels = np.where(
            codes < 0,
            "missing",
            np.where(
                codes < n_special,
                np.char.add("s", codes.astype(str)),
                np.char.add("b", (codes - n_special).astype(str)),
            ),
        )
        return pd.Series(labels, index=values.index)

    def describe(self, code: str) -> dict[str, Any]:
        """Bounds or label of one group code, for the client to render."""
        if code == "missing":
            return {"kind": "missing"}
        if code == "other":
            return {"kind": "other"}
        if code.startswith("c:"):
            return {"kind": "category", "value": code[2:]}
        if code.startswith("s"):
            return {"kind": "special", "value": self.special[int(code[1:])]}
        i = int(code[1:])
        edges = [None, *self.cuts, None]
        return {"kind": "interval", "lower": edges[i], "upper": edges[i + 1]}

    def order(self, codes: list[str]) -> list[str]:
        rank = {"s": 0, "b": 1, "c": 1, "o": 2, "m": 3}

        def key(c: str):
            if c.startswith(("b", "s")) and c[1:].isdigit():
                return (rank[c[0]], int(c[1:]), "")
            return (rank.get(c[0], 2), 0, c)

        return sorted(codes, key=key)


def _trend(woe: np.ndarray) -> str:
    signs = np.sign(np.diff(woe))
    signs = signs[signs != 0]
    if not len(signs):
        return "flat"
    changes = np.count_nonzero(np.diff(signs))
    if changes == 0:
        return "increasing" if signs[0] > 0 else "decreasing"
    return ("peak" if signs[0] > 0 else "valley") if changes == 1 else "irregular"


def iv_level(iv: float) -> str:
    return (
        "useless"
        if iv < 0.02
        else "weak"
        if iv < 0.1
        else "medium"
        if iv < 0.3
        else "strong"
        if iv < 0.5
        else "suspicious"
    )


def _finite(value: float | None, digits: int = 6) -> float | None:
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def fit(values: pd.Series, target: pd.Series, spec: BinSpec, kind: str) -> tuple[Rule, list[str]]:
    """Fit a rule on labelled reference values; returns the rule and kivi's warnings."""
    notes: list[str] = []
    if kind == "category" or spec.method == "category":
        text = values.astype("string").dropna()
        if text.empty:
            raise BinningError("no_observations", "The column has no observed values")
        shares = text.value_counts(normalize=True)
        if len(shares) > MAX_CATEGORIES:
            raise BinningError(
                "too_many_categories",
                "Too many distinct values for category binning",
                count=int(len(shares)),
                limit=MAX_CATEGORIES,
            )
        keep = shares[shares >= spec.min_bin_share].index
        if len(keep) < 2:
            keep = shares.index[: max(2, len(keep))]
        levels = {str(level): f"c:{level}" if level in keep else "other" for level in shares.index}
        return Rule("category", levels=levels), notes

    numbers = pd.to_numeric(values, errors="coerce")
    observed = numbers[~numbers.isin(spec.special)].dropna()
    if observed.empty:
        raise BinningError("no_observations", "The column has no observed numeric values")
    special = spec.special or None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            if spec.method in ("quantile", "uniform"):
                edges = bin_edges(numbers.dropna(), spec.bins, spec.method, special=special)
            elif spec.method == "chimerge":
                edges = chimerge_edges(numbers, target, max_bins=spec.bins, alpha=spec.alpha, special=special)
            elif spec.method == "tree":
                edges = tree_edges(
                    numbers, target, max_bins=spec.bins, min_bin_share=spec.min_bin_share, special=special
                )
            elif spec.method == "monotonic":
                edges = monotonic_edges(
                    numbers, target, max_bins=spec.bins, direction=spec.direction, special=special
                )
            else:
                edges = np.array([-np.inf, *spec.cuts, np.inf])
        except ValueError as error:
            raise BinningError("binning_failed", str(error)) from error
    notes.extend(str(w.message) for w in caught)
    cuts = [float(e) for e in np.asarray(edges)[1:-1]]
    return Rule("numeric", cuts=cuts, special=list(spec.special)), notes


def report(rule: Rule, values: pd.Series, target: pd.Series) -> dict[str, Any]:
    """Bin table with kivi's WOE and IV for labelled observations."""
    groups = rule.assign(values)
    table = woe_table(groups, target)
    total = int((table.event + table.non_event).sum())
    rows = []
    for code in rule.order([str(c) for c in table.index]):
        row = table.loc[code]
        count = int(row.event + row.non_event)
        rows.append(
            {
                "code": code,
                **rule.describe(code),
                "count": count,
                "share": _finite(count / total),
                "bad": int(row.event),
                "good": int(row.non_event),
                "bad_rate": _finite(row.event / count if count else None),
                "woe": _finite(row.woe),
                "iv": _finite(row.iv),
            }
        )
    ordinary = [r["woe"] for r in rows if r["kind"] == "interval"]
    trend = _trend(np.array(ordinary)) if rule.kind == "numeric" else "unordered"
    iv = float(sum(r["iv"] or 0 for r in rows))
    return {
        "bins": rows,
        "iv": _finite(iv),
        "level": iv_level(iv),
        "trend": trend,
        "missing_rate": _finite(float(values.isna().mean())),
        "rows": total,
        "bad_rate": _finite(float(target.mean())),
    }


def psi(rule: Rule, reference: pd.Series, current: pd.Series) -> float:
    return float(psi_table(rule.assign(reference), rule.assign(current)).psi.sum())


def psi_table_value(reference: pd.Series, current: pd.Series) -> float:
    """PSI between two samples that are already assigned to group codes."""
    return float(psi_table(reference.reset_index(drop=True), current.reset_index(drop=True)).psi.sum())
