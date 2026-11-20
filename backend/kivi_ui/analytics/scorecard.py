"""Scorecard development and monitoring on a labelled application sample.

Binning, weight of evidence, information value and population stability use
kivi (``bin_edges``, ``woe_table``, ``psi_table``). The logistic fit and ROC
metrics use scikit-learn. The result is a JSON-ready dictionary that the web
client renders; every label is either a code or carries both languages.
"""

import warnings
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from kivi.binning import bin_edges
from kivi.evaluate import psi_table
from kivi.woe import woe_table
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve

from .sample import CATEGORIES, FEATURES, Feature

TRAIN_MONTHS = 9
MIN_IV = 0.02
MAX_FEATURES = 8
# Score = OFFSET + FACTOR * ln(good:bad odds); 600 points at 20:1, 50 points to double the odds.
BASE_SCORE, BASE_ODDS, PDO = 600, 20, 50
FACTOR = PDO / np.log(2)
OFFSET = BASE_SCORE - FACTOR * np.log(BASE_ODDS)
SCORE_BANDS = [-np.inf, 450, 500, 530, 560, 590, 620, 650, 700, np.inf]
PSI_WARN, PSI_ALERT = 0.10, 0.25
MISSING = -1


def _f(value: float | None, digits: int = 4) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), digits)


def _iv_level(iv: float) -> str:
    if iv < 0.02:
        return "useless"
    if iv < 0.1:
        return "weak"
    if iv < 0.3:
        return "medium"
    if iv < 0.5:
        return "strong"
    return "suspicious"


def _trend(woe: np.ndarray) -> str:
    signs = np.sign(np.diff(woe))
    signs = signs[signs != 0]
    if not len(signs):
        return "flat"
    changes = np.count_nonzero(np.diff(signs))
    if changes == 0:
        return "increasing" if signs[0] > 0 else "decreasing"
    return ("peak" if signs[0] > 0 else "valley") if changes == 1 else "irregular"


def _psi_level(value: float) -> str:
    return "alert" if value >= PSI_ALERT else "warn" if value >= PSI_WARN else "normal"


@dataclass
class Encoder:
    """A frozen binning of one feature, fitted on the training months."""

    feature: Feature
    edges: np.ndarray | None
    woe: pd.Series  # bin code -> WOE

    def groups(self, values: pd.Series) -> pd.Series:
        if self.edges is None:
            return values.astype(str)
        codes = pd.cut(values, self.edges, labels=False)
        return codes.fillna(MISSING).astype(int)

    def transform(self, values: pd.Series) -> pd.Series:
        return self.groups(values).map(self.woe).fillna(0.0).astype(float)


def _bin_rows(feature: Feature, edges: np.ndarray | None, table: pd.DataFrame) -> list[dict]:
    rows = []
    total = (table.event + table.non_event).sum()
    for code, row in table.iterrows():
        count = int(row.event + row.non_event)
        item: dict[str, Any] = {
            "code": code if isinstance(code, str) else int(code),
            "count": count,
            "share": _f(count / total),
            "bad": int(row.event),
            "good": int(row.non_event),
            "bad_rate": _f(row.event / count if count else None),
            "woe": _f(row.woe),
            "iv": _f(row.iv),
        }
        if edges is not None:
            item["missing"] = bool(code == MISSING)
            if code != MISSING:
                lower, upper = edges[int(code)], edges[int(code) + 1]
                item["lower"] = None if np.isinf(lower) else _f(lower, 6)
                item["upper"] = None if np.isinf(upper) else _f(upper, 6)
        else:
            zh, en = CATEGORIES[feature.name][code]
            item["label"] = {"zh": zh, "en": en}
        rows.append(item)
    return rows


def _fit_feature(feature: Feature, values: pd.Series, target: pd.Series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # tied quantiles merge bins, as intended here
        edges = bin_edges(values, feature.bins) if feature.kind == "numeric" else None
    encoder = Encoder(feature, edges, pd.Series(dtype=float))
    table = woe_table(encoder.groups(values), target)
    if edges is not None:
        order = sorted(table.index, key=lambda c: (c == MISSING, c))
    else:
        order = table.sort_values("woe").index.tolist()
    table = table.loc[order]
    encoder.woe = table.woe
    ordinary = table.loc[[c for c in order if c != MISSING]]
    trend = _trend(ordinary.woe.to_numpy()) if edges is not None else "unordered"
    iv = float(table.iv.sum())
    summary = {
        "name": feature.name,
        "label": {"zh": feature.zh, "en": feature.en},
        "kind": feature.kind,
        "unit": feature.unit,
        "iv": _f(iv),
        "level": _iv_level(iv),
        "trend": trend,
        "missing_rate": _f(values.isna().mean()),
        "bins": _bin_rows(feature, edges, table),
    }
    return encoder, summary


def _score(probability: np.ndarray) -> np.ndarray:
    p = np.clip(probability, 1e-6, 1 - 1e-6)
    return np.round(OFFSET + FACTOR * np.log((1 - p) / p))


def _roc(target: pd.Series, risk: np.ndarray, points: int = 41) -> dict[str, Any]:
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


def _band_codes(score: pd.Series) -> pd.Series:
    return pd.Series(pd.cut(score, SCORE_BANDS, labels=False, right=False), index=score.index)


def _bands(score: pd.Series, target: pd.Series) -> list[dict]:
    codes = _band_codes(score)
    rows = []
    for code in range(len(SCORE_BANDS) - 1):
        mask = codes == code
        n, bad = int(mask.sum()), int(target[mask].sum())
        lower, upper = SCORE_BANDS[code], SCORE_BANDS[code + 1]
        rows.append(
            {
                "band": code,
                "lower": None if np.isinf(lower) else int(lower),
                "upper": None if np.isinf(upper) else int(upper),
                "count": n,
                "share": _f(n / len(score)),
                "bad": bad,
                "bad_rate": _f(bad / n if n else None),
            }
        )
    return rows


def _gains(score: pd.Series, target: pd.Series, groups: int = 10) -> list[dict]:
    order = np.argsort(score.to_numpy(), kind="stable")  # riskiest first
    s, y = score.to_numpy()[order], target.to_numpy()[order]
    chunks = np.array_split(np.arange(len(s)), groups)
    total_bad, total_good = y.sum(), len(y) - y.sum()
    rows, cum_bad, cum_good = [], 0, 0
    for i, idx in enumerate(chunks, start=1):
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
                "cum_bad_pct": _f(cum_bad / total_bad),
                "cum_good_pct": _f(cum_good / total_good),
                "ks": _f(cum_bad / total_bad - cum_good / total_good),
                "lift": _f((bad / len(idx)) / (total_bad / len(y))),
            }
        )
    return rows


def _psi(reference: pd.Series, current: pd.Series) -> float:
    return float(psi_table(reference, current).psi.sum())


# ---- Strategy simulation --------------------------------------------------------------------

RULES: tuple[dict[str, Any], ...] = (
    {"code": "R01", "decision": "reject", "zh": "年龄不在 20–60 岁", "en": "Age outside 20–60"},
    {"code": "R02", "decision": "reject", "zh": "近24月逾期 ≥ 3 次", "en": "3+ delinquencies (24m)"},
    {"code": "R03", "decision": "reject", "zh": "近6月查询 ≥ 9 次", "en": "9+ inquiries (6m)"},
    {"code": "R04", "decision": "reject", "zh": "负债收入比 > 0.85", "en": "Debt-to-income > 0.85"},
    {"code": "R05", "decision": "reject", "zh": "评分 < 520", "en": "Score below 520"},
    {"code": "R06", "decision": "review", "zh": "评分 520–560 人工审核", "en": "Score 520–560 to review"},
    {"code": "R07", "decision": "review", "zh": "合作渠道且评分 < 590", "en": "Partner channel, score < 590"},
)


def _rule_hits(frame: pd.DataFrame, score: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "R01": (frame.age < 20) | (frame.age > 60),
            "R02": frame.overdue_24m >= 3,
            "R03": frame.inquiries_6m >= 9,
            "R04": frame.debt_ratio > 0.85,
            "R05": score < 520,
            "R06": (score >= 520) & (score < 560),
            "R07": (frame.channel == "partner") & (score < 590),
        },
        index=frame.index,
    )


def _decide(hits: pd.DataFrame) -> pd.Series:
    rejects = [r["code"] for r in RULES if r["decision"] == "reject"]
    reviews = [r["code"] for r in RULES if r["decision"] == "review"]
    decision = pd.Series("pass", index=hits.index)
    decision[hits[reviews].any(axis=1)] = "review"
    decision[hits[rejects].any(axis=1)] = "reject"
    return decision


def _decision_counts(decision: pd.Series) -> dict[str, Any]:
    counts = decision.value_counts()
    total = int(len(decision))
    out = {k: int(counts.get(k, 0)) for k in ("pass", "review", "reject")}
    out["total"] = total
    out["approval_rate"] = _f(out["pass"] / total if total else None)
    return out


# ---- Payload --------------------------------------------------------------------------------


def build(sample: pd.DataFrame, as_of: date) -> dict[str, Any]:
    train = sample[sample.month_index < TRAIN_MONTHS]
    oot = sample[sample.month_index >= TRAIN_MONTHS]
    y_train, y_oot = train.target, oot.target

    encoders, indicators = {}, []
    for feature in FEATURES:
        encoder, summary = _fit_feature(feature, train[feature.name], y_train)
        encoders[feature.name] = encoder
        indicators.append(summary)
    indicators.sort(key=lambda s: -s["iv"])

    selected = [s["name"] for s in indicators if s["iv"] >= MIN_IV][:MAX_FEATURES]
    for s in indicators:
        s["selected"] = s["name"] in selected

    def design(frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({n: encoders[n].transform(frame[n]) for n in selected})

    model = LogisticRegression(C=1.0, max_iter=2000).fit(design(train), y_train)
    p_all = model.predict_proba(design(sample))[:, 1]
    score = pd.Series(_score(p_all), index=sample.index)
    s_train, s_oot = score[train.index], score[oot.index]
    p_train = pd.Series(p_all, index=sample.index)[train.index]
    p_oot = pd.Series(p_all, index=sample.index)[oot.index]

    coefficients = dict(zip(selected, model.coef_[0], strict=True))
    base_points = OFFSET - FACTOR * model.intercept_[0]
    scorecard = []
    for name in selected:
        summary = next(s for s in indicators if s["name"] == name)
        bins = []
        for b in summary["bins"]:
            points = -FACTOR * coefficients[name] * (b["woe"] or 0.0) + base_points / len(selected)
            bins.append(
                {
                    **{k: b.get(k) for k in ("code", "lower", "upper", "missing", "label")},
                    "woe": b["woe"],
                    "points": int(round(points)),
                }
            )
        scorecard.append(
            {
                "name": name,
                "label": summary["label"],
                "unit": summary["unit"],
                "kind": summary["kind"],
                "coefficient": _f(coefficients[name]),
                "bins": bins,
            }
        )

    roc_train, roc_oot = _roc(y_train, p_train.to_numpy()), _roc(y_oot, p_oot.to_numpy())
    score_psi = _psi(_band_codes(s_train), _band_codes(s_oot))

    # Monthly monitoring against the training reference.
    train_bands = _band_codes(s_train)
    train_groups = {n: encoders[n].groups(train[n]) for n in encoders}
    hits = _rule_hits(sample, score)
    decision = _decide(hits)
    monthly, feature_psi = [], {s["name"]: [] for s in indicators}
    for month, part in sample.groupby("month", sort=True):
        y, s = part.target, score[part.index]
        roc = _roc(y, (-s).to_numpy()) if y.nunique() == 2 else None
        monthly.append(
            {
                "month": month,
                "in_reference": bool(part.month_index.iloc[0] < TRAIN_MONTHS),
                "applications": int(len(part)),
                "bad_rate": _f(y.mean()),
                "mean_score": _f(s.mean(), 1),
                "score_psi": _f(_psi(train_bands, _band_codes(s))),
                "auc": roc and roc["auc"],
                "ks": roc and roc["ks"],
                "approval_rate": _decision_counts(decision[part.index])["approval_rate"],
            }
        )
        for name, encoder in encoders.items():
            feature_psi[name].append(_f(_psi(train_groups[name], encoder.groups(part[name]))))

    # Daily decisions over the last 30 days, and the 30 days before for comparison.
    days = sample.applied_on.dt.date
    last = (days > as_of - timedelta(days=30)) & (days <= as_of)
    prior = (days > as_of - timedelta(days=60)) & (days <= as_of - timedelta(days=30))
    daily = []
    for offset in range(29, -1, -1):
        day = as_of - timedelta(days=offset)
        counts = _decision_counts(decision[days == day])
        daily.append({"date": day.isoformat(), **counts})
    current, previous = _decision_counts(decision[last]), _decision_counts(decision[prior])

    rule_rows = []
    rejects = [r["code"] for r in RULES if r["decision"] == "reject"]
    window = hits[last]
    for rule in RULES:
        hit = window[rule["code"]]
        others = window[[c for c in rejects if c != rule["code"]]].any(axis=1)
        rule_rows.append(
            {
                "code": rule["code"],
                "label": {"zh": rule["zh"], "en": rule["en"]},
                "decision": rule["decision"],
                "hits": int(hit.sum()),
                "hit_rate": _f(hit.mean()),
                "exclusive": int((hit & ~others).sum()),
            }
        )

    labelled = sample[sample.month_index < TRAIN_MONTHS]
    effect = {
        k: _f(labelled.target[decision[labelled.index] == k].mean()) for k in ("pass", "review", "reject")
    }

    # Alerts: latest month against thresholds.
    latest = monthly[-1]
    alerts = []
    for name, series in feature_psi.items():
        value = series[-1] or 0.0
        if value >= PSI_WARN:
            summary = next(s for s in indicators if s["name"] == name)
            alerts.append(
                {
                    "kind": "feature_psi",
                    "level": _psi_level(value),
                    "subject": name,
                    "subject_label": summary["label"],
                    "value": _f(value),
                    "threshold": PSI_ALERT if value >= PSI_ALERT else PSI_WARN,
                    "month": latest["month"],
                }
            )
    if (latest["score_psi"] or 0) >= PSI_WARN:
        alerts.append(
            {
                "kind": "score_psi",
                "level": _psi_level(latest["score_psi"]),
                "value": latest["score_psi"],
                "month": latest["month"],
                "threshold": PSI_ALERT if latest["score_psi"] >= PSI_ALERT else PSI_WARN,
            }
        )
    ks_drop = 1 - (roc_oot["ks"] or 0) / (roc_train["ks"] or 1)
    if ks_drop >= 0.05:
        alerts.append(
            {
                "kind": "ks_drop",
                "level": "alert" if ks_drop >= 0.15 else "warn",
                "value": _f(ks_drop),
                "train": roc_train["ks"],
                "oot": roc_oot["ks"],
            }
        )
    shift = (current["approval_rate"] or 0) - (previous["approval_rate"] or 0)
    if abs(shift) >= 0.03:
        alerts.append(
            {
                "kind": "approval_shift",
                "level": "alert" if abs(shift) >= 0.06 else "warn",
                "value": _f(shift),
                "current": current["approval_rate"],
                "previous": previous["approval_rate"],
            }
        )
    severity = {"alert": 0, "warn": 1}
    alerts.sort(key=lambda a: (severity[a["level"]], -(abs(a.get("value") or 0))))
    for i, alert in enumerate(alerts, start=1):
        alert["id"] = f"AL{i:03d}"

    return {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "as_of": as_of.isoformat(),
            "engine": "kivi",
            "sample": {
                "rows": int(len(sample)),
                "bad_rate": _f(sample.target.mean()),
                "months": [m for m in sorted(sample.month.unique())],
                "train_rows": int(len(train)),
                "oot_rows": int(len(oot)),
                "train_months": [sorted(train.month.unique())[i] for i in (0, -1)],
                "oot_months": [sorted(oot.month.unique())[i] for i in (0, -1)],
                "features": len(FEATURES),
            },
        },
        "kpis": {
            "applications_30d": current["total"],
            "applications_prev_30d": previous["total"],
            "approval_rate_30d": current["approval_rate"],
            "approval_rate_prev_30d": previous["approval_rate"],
            "review_rate_30d": _f(current["review"] / current["total"]),
            "reject_rate_30d": _f(current["reject"] / current["total"]),
            "auc_oot": roc_oot["auc"],
            "auc_train": roc_train["auc"],
            "ks_oot": roc_oot["ks"],
            "ks_train": roc_train["ks"],
            "score_psi_latest": latest["score_psi"],
            "score_psi_oot": _f(score_psi),
            "alerts": {
                "alert": sum(a["level"] == "alert" for a in alerts),
                "warn": sum(a["level"] == "warn" for a in alerts),
            },
        },
        "decisions": {
            "daily": daily,
            "rules": rule_rows,
            "effect": effect,
            "current": current,
            "previous": previous,
        },
        "indicators": indicators,
        "model": {
            "code": "RETAIL_A_CARD",
            "name": {"zh": "零售信贷申请评分卡", "en": "Retail application scorecard"},
            "version": "v1",
            "features": selected,
            "intercept": _f(model.intercept_[0]),
            "scale": {"base_score": BASE_SCORE, "base_odds": BASE_ODDS, "pdo": PDO},
            "scorecard": scorecard,
            "roc": {"train": roc_train, "oot": roc_oot},
            "bands": {"train": _bands(s_train, y_train), "oot": _bands(s_oot, y_oot)},
            "gains": _gains(s_oot, y_oot),
            "score_stats": {"min": int(score.min()), "max": int(score.max()), "mean": _f(score.mean(), 1)},
        },
        "stability": {
            "thresholds": {"warn": PSI_WARN, "alert": PSI_ALERT},
            "monthly": monthly,
            "feature_psi": [
                {"name": s["name"], "label": s["label"], "values": feature_psi[s["name"]]} for s in indicators
            ],
        },
        "alerts": alerts,
    }
