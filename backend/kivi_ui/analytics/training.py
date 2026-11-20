"""Scorecard development: split, bin, select, fit, scale and evaluate.

Binning rules are refitted on the training rows only, with each indicator's
saved spec, so test and out-of-time (OOT) metrics are honest. Variables are
selected in logged steps: information value, variance inflation, coefficient
sign and significance. The logistic fit uses statsmodels for p-values; WOE,
IV and PSI come from kivi through :mod:`kivi_ui.analytics.binning`.
"""

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from pydantic import BaseModel, Field
from statsmodels.stats.outliers_influence import variance_inflation_factor

from . import binning, metrics
from .binning import BinningError, BinSpec


class TrainConfig(BaseModel):
    oot_months: int = Field(3, ge=0, le=24, description="Last N months held out as out-of-time")
    test_ratio: float = Field(0.3, ge=0, le=0.5, description="Random share of in-time rows held out")
    seed: int = 42
    iv_min: float = Field(0.02, ge=0, le=1)
    vif_max: float = Field(5.0, ge=1, le=100)
    p_max: float = Field(0.05, gt=0, le=1)
    require_positive: bool = Field(True, description="Drop variables whose WOE coefficient is not positive")
    max_features: int = Field(12, ge=1, le=40)
    base_score: int = Field(600, ge=100, le=1000)
    base_odds: float = Field(20, gt=0, le=1000)
    pdo: float = Field(50, gt=0, le=200)


class TrainingError(ValueError):
    def __init__(self, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.code, self.detail = code, detail


@dataclass
class Candidate:
    indicator_id: str
    code: str
    name: str
    name_en: str | None
    column: str
    kind: str
    unit: str | None
    spec: dict[str, Any]
    header: str | None = None  # the column's header as uploaded; scoring matches on it


def _f(value, digits: int = 6):
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def split_rows(index: pd.Index, dates: pd.Series | None, config: TrainConfig) -> tuple[pd.Series, list[str]]:
    """Label each row train / test / oot."""
    notes: list[str] = []
    split = pd.Series("train", index=index)
    if dates is not None and config.oot_months:
        months = pd.to_datetime(dates, errors="coerce").dt.to_period("M")
        ordered = sorted(months.dropna().unique())
        if len(ordered) > config.oot_months:
            split[months.isin(ordered[-config.oot_months :])] = "oot"
        else:
            notes.append("too_few_months_for_oot")
    elif config.oot_months:
        notes.append("no_date_for_oot")
    if config.test_ratio:
        in_time = split.index[split == "train"]
        rng = np.random.default_rng(config.seed)
        chosen = rng.choice(len(in_time), size=int(round(len(in_time) * config.test_ratio)), replace=False)
        split[in_time[chosen]] = "test"
    return split, notes


def _vif(frame: pd.DataFrame) -> pd.Series:
    if frame.shape[1] < 2:
        return pd.Series(1.0, index=frame.columns)
    design = sm.add_constant(frame, has_constant="add").to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        values = [variance_inflation_factor(design, i + 1) for i in range(frame.shape[1])]
    return pd.Series(values, index=frame.columns).replace([np.inf, np.nan], 1e6)


def _logit(x: pd.DataFrame, y: pd.Series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fit = sm.Logit(y.astype(float), sm.add_constant(x, has_constant="add")).fit(disp=0, maxiter=200)
        except (np.linalg.LinAlgError, ValueError) as error:
            raise TrainingError(
                "fit_failed", f"The logistic regression could not be fitted: {error}"
            ) from error
    if not fit.mle_retvals.get("converged", True):
        raise TrainingError("fit_failed", "The logistic regression did not converge")
    return fit


def train(
    frame: pd.DataFrame,
    y: pd.Series,
    dates: pd.Series | None,
    candidates: list[Candidate],
    config: TrainConfig,
) -> dict[str, Any]:
    """Develop a scorecard on labelled rows. `frame` holds the candidates' columns."""
    split, notes = split_rows(frame.index, dates, config)
    train_idx = split.index[split == "train"]
    y_train = y[train_idx]
    if y_train.sum() < 20 or (len(y_train) - y_train.sum()) < 20:
        raise TrainingError(
            "too_few_events",
            "The training sample needs at least 20 bad and 20 good rows",
            bad=int(y_train.sum()),
            rows=int(len(y_train)),
        )

    # 1. Bin each candidate on the training rows and encode every row with its WOE.
    encoded, fitted, screening, steps = {}, {}, [], []
    for c in candidates:
        values = frame[c.column]
        spec = BinSpec(**c.spec)
        if c.kind == "category":
            spec = spec.model_copy(update={"method": "category"})
        try:
            rule, _ = binning.fit(values[train_idx], y_train, spec, c.kind)
            report = binning.report(rule, values[train_idx], y_train)
        except BinningError as error:
            screening.append(
                {
                    "code": c.code,
                    "name": c.name,
                    "name_en": c.name_en,
                    "iv": None,
                    "selected": False,
                    "reason": "binning_failed",
                    "detail": str(error),
                }
            )
            continue
        woe = {b["code"]: b["woe"] for b in report["bins"]}
        encoded[c.code] = rule.assign(values).map(woe).fillna(0.0).astype(float)
        fitted[c.code] = (c, rule, report, spec)
        screening.append(
            {
                "code": c.code,
                "name": c.name,
                "name_en": c.name_en,
                "iv": report["iv"],
                "selected": True,
                "reason": None,
            }
        )

    by_code = {s["code"]: s for s in screening}

    def drop(code: str, reason: str, value: float | None = None) -> None:
        by_code[code].update(selected=False, reason=reason, value=_f(value))
        steps.append({"rule": reason, "feature": code, "value": _f(value)})

    # 2. Information value floor, then the strongest `max_features`.
    keep = [code for code in fitted if (fitted[code][2]["iv"] or 0) >= config.iv_min]
    for code in fitted:
        if code not in keep:
            drop(code, "iv", fitted[code][2]["iv"])
    keep.sort(key=lambda code: -(fitted[code][2]["iv"] or 0))
    for code in keep[config.max_features :]:
        drop(code, "max_features", fitted[code][2]["iv"])
    keep = keep[: config.max_features]
    if not keep:
        raise TrainingError("no_features_left", "No candidate passed the information value floor")

    x_all = pd.DataFrame(encoded)
    x_train = x_all.loc[train_idx]

    # 3. Variance inflation: drop the most collinear variable until all are below the limit.
    while len(keep) > 1:
        vif = _vif(x_train[keep])
        worst = vif.idxmax()
        if vif[worst] <= config.vif_max:
            break
        keep.remove(worst)
        drop(worst, "vif", vif[worst])

    # 4. Coefficient sign and significance, refitting after each removal.
    while True:
        if not keep:
            raise TrainingError("no_features_left", "Every candidate was removed during selection")
        fit = _logit(x_train[keep], y_train)
        coef = fit.params[keep]
        if config.require_positive and (coef <= 0).any():
            worst = coef.idxmin()
            keep.remove(worst)
            drop(worst, "sign", coef[worst])
            continue
        pvalues = fit.pvalues[keep]
        if (pvalues > config.p_max).any() and len(keep) > 1:
            worst = pvalues.idxmax()
            keep.remove(worst)
            drop(worst, "pvalue", pvalues[worst])
            continue
        break

    # 5. Scale and score every row.
    factor, offset = metrics.pdo_scale(config.base_score, config.base_odds, config.pdo)
    intercept = float(fit.params["const"])
    logit = intercept + x_all[keep].to_numpy() @ fit.params[keep].to_numpy()
    probability = pd.Series(1 / (1 + np.exp(-logit)), index=frame.index)
    score = pd.Series(metrics.to_score(probability.to_numpy(), factor, offset), index=frame.index)

    # 6. Evaluate each split.
    present = [s for s in ("train", "test", "oot") if (split == s).any()]
    evaluation: dict[str, Any] = {}
    for name in present:
        idx = split.index[split == name]
        ys = y[idx]
        entry: dict[str, Any] = {"rows": int(len(idx)), "bad": int(ys.sum()), "bad_rate": _f(ys.mean())}
        if dates is not None:
            d = pd.to_datetime(dates[idx], errors="coerce").dropna()
            entry["period"] = [str(d.min().to_period("M")), str(d.max().to_period("M"))] if len(d) else None
        if ys.nunique() == 2:
            entry["roc"] = metrics.roc(ys, probability[idx].to_numpy())
        evaluation[name] = entry
    cuts = metrics.band_edges(score[train_idx])
    reference_bands = metrics.band_codes(score[train_idx], cuts)
    for name in present:
        idx = split.index[split == name]
        evaluation[name]["bands"] = metrics.bands(score[idx], y[idx], cuts)
        if name != "train":
            evaluation[name]["psi"] = _f(metrics.psi(reference_bands, metrics.band_codes(score[idx], cuts)))
    focus = "oot" if "oot" in present else "test" if "test" in present else "train"
    focus_idx = split.index[split == focus]

    # 7. Scorecard points and per-variable diagnostics.
    final_vif = _vif(x_train[keep])
    base_points = offset - factor * intercept
    features = []
    for code in keep:
        c, rule, report, spec = fitted[code]
        coefficient = float(fit.params[code])
        bins = [
            {**b, "points": int(round(-factor * coefficient * (b["woe"] or 0) + base_points / len(keep)))}
            for b in report["bins"]
        ]
        groups = rule.assign(frame[c.column])
        stability = {
            name: _f(metrics.psi(groups[train_idx], groups[split.index[split == name]]))
            for name in present
            if name != "train"
        }
        features.append(
            {
                "indicator_id": c.indicator_id,
                "code": code,
                "name": c.name,
                "name_en": c.name_en,
                "column": c.column,
                "header": c.header,
                "kind": c.kind,
                "unit": c.unit,
                "coefficient": _f(coefficient),
                "std_err": _f(float(fit.bse[code])),
                "p_value": float(f"{float(fit.pvalues[code]):.4g}"),
                "vif": _f(float(final_vif[code]), 4),
                "iv": report["iv"],
                "trend": report["trend"],
                "psi": stability,
                "spec": spec.model_dump(),
                "rule": rule.to_dict(),
                "bins": bins,
            }
        )
    features.sort(key=lambda f: -(f["iv"] or 0))

    return {
        "features": features,
        "intercept": _f(intercept),
        "scale": {
            "base_score": config.base_score,
            "base_odds": config.base_odds,
            "pdo": config.pdo,
            "factor": _f(factor),
            "offset": _f(offset),
        },
        "evaluation": evaluation,
        "focus": focus,
        "gains": metrics.gains(score[focus_idx], y[focus_idx]),
        "score_stats": {
            "min": int(score.min()),
            "max": int(score.max()),
            "mean": _f(score[train_idx].mean(), 1),
        },
        "band_cuts": cuts,
        "selection": {"candidates": screening, "steps": steps},
        "fit": {
            "pseudo_r2": _f(float(fit.prsquared)),
            "log_likelihood": _f(float(fit.llf)),
            "aic": _f(float(fit.aic)),
            "rows": int(len(train_idx)),
        },
        "notes": notes,
    }


def score_frame(result: dict[str, Any], frame: pd.DataFrame) -> pd.DataFrame:
    """Apply a trained version to new rows: probability and score."""
    logit = np.full(len(frame), float(result["intercept"]))
    for feature in result["features"]:
        rule = binning.Rule.from_dict(feature["rule"])
        woe = {b["code"]: b["woe"] for b in feature["bins"]}
        encoded = rule.assign(frame[feature["column"]]).map(woe).fillna(0.0).astype(float).to_numpy()
        logit += float(feature["coefficient"]) * encoded
    probability = 1 / (1 + np.exp(-logit))
    scale = result["scale"]
    score = metrics.to_score(probability, float(scale["factor"]), float(scale["offset"]))
    return pd.DataFrame(
        {"score": score.astype(int), "probability": np.round(probability, 6)}, index=frame.index
    )
