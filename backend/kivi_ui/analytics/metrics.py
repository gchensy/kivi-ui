"""Model evaluation helpers: ROC, gains, score bands and PSI."""

from typing import Any

import numpy as np
import pandas as pd
from kivi.evaluate import psi_table
from sklearn.metrics import roc_auc_score, roc_curve


def _f(value: float | None, digits: int = 4) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), digits)


def pdo_scale(base_score: float, base_odds: float, pdo: float) -> tuple[float, float]:
    """(factor, offset) so that score = offset + factor * ln(good:bad odds)."""
    factor = pdo / np.log(2)
    return factor, base_score - factor * np.log(base_odds)


def to_score(probability: np.ndarray, factor: float, offset: float) -> np.ndarray:
    p = np.clip(probability, 1e-6, 1 - 1e-6)
    return np.round(offset + factor * np.log((1 - p) / p))


def roc(target: pd.Series, risk: np.ndarray, points: int = 41) -> dict[str, Any]:
    """AUC, KS, Gini and a resampled ROC curve; `risk` grows with the event probability."""
    fpr, tpr, _ = roc_curve(target, risk)
    grid = np.linspace(0, 1, points)
    curve = np.interp(grid, fpr, tpr)
    auc = roc_auc_score(target, risk)
    return {
        "auc": _f(auc),
        "ks": _f(np.max(tpr - fpr)),
        "gini": _f(2 * auc - 1),
        "curve": [{"fpr": _f(x, 3), "tpr": _f(y, 4)} for x, y in zip(grid, curve, strict=True)],
    }


def gains(score: pd.Series, target: pd.Series, groups: int = 10) -> list[dict[str, Any]]:
    """Equal-count groups from the lowest (riskiest) score up, with cumulative capture and KS."""
    order = np.argsort(score.to_numpy(), kind="stable")
    s, y = score.to_numpy()[order], target.to_numpy()[order]
    chunks = np.array_split(np.arange(len(s)), groups)
    total_bad, total_good = y.sum(), len(y) - y.sum()
    rows, cum_bad, cum_good = [], 0, 0
    for i, idx in enumerate(chunks, start=1):
        if not len(idx):
            continue
        bad = int(y[idx].sum())
        good = len(idx) - bad
        cum_bad, cum_good = cum_bad + bad, cum_good + good
        rows.append(
            {
                "decile": i,
                "min_score": int(s[idx].min()),
                "max_score": int(s[idx].max()),
                "count": len(idx),
                "bad": bad,
                "bad_rate": _f(bad / len(idx)),
                "cum_bad_pct": _f(cum_bad / total_bad if total_bad else None),
                "cum_good_pct": _f(cum_good / total_good if total_good else None),
                "ks": _f(cum_bad / total_bad - cum_good / total_good if total_bad and total_good else None),
                "lift": _f((bad / len(idx)) / (total_bad / len(y)) if total_bad else None),
            }
        )
    return rows


def band_edges(reference: pd.Series, groups: int = 10) -> list[float]:
    """Interior cut points at the reference score's deciles (integers, unique)."""
    cuts = np.unique(np.round(np.quantile(reference.to_numpy(), np.linspace(0, 1, groups + 1)[1:-1])))
    return [float(c) for c in cuts]


def band_codes(score: pd.Series, cuts: list[float]) -> pd.Series:
    return pd.Series(pd.cut(score, [-np.inf, *cuts, np.inf], labels=False, right=False), index=score.index)


def bands(score: pd.Series, target: pd.Series, cuts: list[float]) -> list[dict[str, Any]]:
    codes = band_codes(score, cuts)
    edges = [None, *cuts, None]
    rows = []
    for code in range(len(cuts) + 1):
        mask = codes == code
        n, bad = int(mask.sum()), int(target[mask].sum())
        rows.append(
            {
                "band": code,
                "lower": None if edges[code] is None else int(edges[code]),
                "upper": None if edges[code + 1] is None else int(edges[code + 1]),
                "count": n,
                "share": _f(n / len(score) if len(score) else None),
                "bad": bad,
                "bad_rate": _f(bad / n if n else None),
            }
        )
    return rows


def psi(reference: pd.Series, current: pd.Series) -> float:
    """PSI between two already-grouped samples."""
    return float(psi_table(reference.reset_index(drop=True), current.reset_index(drop=True)).psi.sum())
