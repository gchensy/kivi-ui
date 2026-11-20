"""A reproducible, simulated retail credit application sample.

Twelve monthly cohorts end in the month of ``as_of``. Applicants share a latent
credit quality that drives both their attributes and their default label, so
the features carry genuine, varied information value. In the last three months
the partner channel grows and credit inquiries rise, which gives the stability
monitors a realistic drift to detect.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Feature:
    name: str
    zh: str
    en: str
    kind: str  # "numeric" | "category"
    unit: str | None = None
    bins: int = 5


FEATURES: tuple[Feature, ...] = (
    Feature("overdue_24m", "近24月逾期次数", "Delinquencies (24m)", "numeric", "count"),
    Feature("inquiries_6m", "近6月征信查询次数", "Credit inquiries (6m)", "numeric", "count"),
    Feature("credit_utilization", "信用卡额度使用率", "Card utilization", "numeric", "ratio"),
    Feature("debt_ratio", "负债收入比", "Debt-to-income", "numeric", "ratio"),
    Feature("monthly_income", "月收入", "Monthly income", "numeric", "cny"),
    Feature("employment_years", "工作年限", "Years employed", "numeric", "years"),
    Feature("age", "年龄", "Age", "numeric", "years"),
    Feature("loan_amount", "申请金额", "Requested amount", "numeric", "cny"),
    Feature("channel", "进件渠道", "Channel", "category"),
    Feature("housing", "住房情况", "Housing", "category"),
    Feature("education", "学历", "Education", "category"),
    Feature("loan_term", "申请期限", "Loan term", "category"),
)

CATEGORIES: dict[str, dict[str, tuple[str, str]]] = {
    "channel": {
        "app": ("自营 APP", "Own app"),
        "branch": ("线下门店", "Branch"),
        "partner": ("合作渠道", "Partner"),
    },
    "housing": {
        "own": ("自有住房", "Owner"),
        "mortgage": ("按揭住房", "Mortgage"),
        "rent": ("租房", "Renting"),
        "family": ("与家人同住", "With family"),
    },
    "education": {
        "master": ("硕士及以上", "Postgraduate"),
        "bachelor": ("本科", "Bachelor"),
        "college": ("大专", "College"),
        "school": ("高中及以下", "High school"),
    },
    "loan_term": {
        "6": ("6 期", "6 months"),
        "12": ("12 期", "12 months"),
        "24": ("24 期", "24 months"),
        "36": ("36 期", "36 months"),
    },
}


def _pick(rng: np.random.Generator, levels: list[str], weights: np.ndarray) -> np.ndarray:
    """Draw one level per row from row-specific weights (rows sum to one)."""
    cumulative = np.cumsum(weights / weights.sum(axis=1, keepdims=True), axis=1)
    draws = rng.random(len(weights))[:, None]
    return np.asarray(levels)[(draws > cumulative).sum(axis=1)]


def simulate(as_of: date, *, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = pd.Period(as_of, freq="M")
    months = pd.period_range(end - 11, end, freq="M")
    volume = np.round(1700 + np.arange(12) * 70 + rng.normal(0, 90, 12)).astype(int)
    volume[-1] = round(volume[-1] * as_of.day / months[-1].days_in_month)  # month to date

    month_index = np.repeat(np.arange(12), volume)
    n = len(month_index)
    drift = np.clip((month_index - 8) / 3, 0, 1)

    # Application dates: uniform within the month, never after as_of.
    starts = np.array([m.start_time.date() for m in months], dtype="datetime64[D]")
    lengths = np.array([m.days_in_month for m in months])
    lengths[-1] = min(lengths[-1], as_of.day)
    day = (rng.random(n) * lengths[month_index]).astype(int)
    applied = starts[month_index] + day.astype("timedelta64[D]")

    channel = _pick(
        rng,
        ["app", "branch", "partner"],
        np.column_stack([0.52 - 0.16 * drift, 0.30 - 0.09 * drift, 0.18 + 0.25 * drift]),
    )
    quality = rng.normal(0, 1, n) - 0.45 * (channel == "partner") + 0.15 * (channel == "branch")

    age = np.clip(np.round(rng.normal(34 + 2.5 * quality, 8.5)), 18, 65)
    income = np.round(np.exp(rng.normal(9.05 + 0.16 * quality - 0.06 * drift, 0.42)), -2)
    debt_ratio = np.clip(rng.normal(0.40 - 0.06 * quality, 0.17), 0.01, 1.6).round(3)
    utilization = (1 / (1 + np.exp(-rng.normal(-0.1 - 0.62 * quality, 0.95)))).round(3)
    inquiries = rng.poisson(np.exp(0.85 - 0.30 * quality + 0.38 * drift))
    overdue = rng.poisson(np.exp(-1.45 - 0.70 * quality))
    employment = np.clip(rng.normal(4.5 + 1.1 * quality + (age - 34) * 0.18, 2.8), 0, 40).round(1)
    amount = np.clip(np.round(np.exp(rng.normal(10.4 + 0.18 * quality, 0.55)), -3), 3000, 300000)

    housing = _pick(
        rng,
        ["own", "mortgage", "rent", "family"],
        np.column_stack(
            [
                np.exp(0.2 + 0.6 * quality),
                np.exp(0.4 + 0.3 * quality),
                np.exp(0.3 - 0.4 * quality),
                np.full(n, np.exp(0.1)),
            ]
        ),
    )
    education = _pick(
        rng,
        ["master", "bachelor", "college", "school"],
        np.column_stack(
            [
                np.exp(-1.2 + 0.7 * quality),
                np.exp(0.5 + 0.25 * quality),
                np.exp(0.3 - 0.2 * quality),
                np.exp(-0.2 - 0.55 * quality),
            ]
        ),
    )
    term = _pick(
        rng,
        ["6", "12", "24", "36"],
        np.column_stack([np.full(n, 0.1), np.full(n, 0.33), np.full(n, 0.35), np.full(n, 0.22)]),
    )

    logit = (
        -3.85
        - 0.72 * quality
        + 0.22 * overdue
        + 0.05 * inquiries
        + 0.9 * (debt_ratio - 0.4)
        + 0.55 * (utilization - 0.5)
        + 0.28 * (term == "36")
        + 0.35 * (channel == "partner")
        + rng.normal(0, 0.6, n)
    )
    target = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)

    frame = pd.DataFrame(
        {
            "application_id": [f"AP{seed:02d}{i:07d}" for i in range(n)],
            "applied_on": pd.to_datetime(applied),
            "month": months[month_index].astype(str),
            "month_index": month_index,
            "age": age.astype(int),
            "monthly_income": income,
            "debt_ratio": debt_ratio,
            "credit_utilization": utilization,
            "inquiries_6m": inquiries,
            "overdue_24m": overdue,
            "employment_years": employment,
            "loan_amount": amount,
            "loan_term": term,
            "housing": housing,
            "education": education,
            "channel": channel,
            "target": target,
        }
    )
    # Synthetic mobile numbers from a separate stream, so every other draw is unchanged.
    phones = np.random.default_rng(seed + 1000).choice(10**9, size=n, replace=False)
    prefixes = np.random.default_rng(seed + 1001).choice([13, 15, 17, 18, 19], size=n)
    frame.insert(2, "phone", [f"{p}{x:09d}" for p, x in zip(prefixes, phones, strict=True)])
    # Unreported income and employment, as in real application data.
    frame.loc[rng.random(n) < 0.03, "monthly_income"] = np.nan
    frame.loc[rng.random(n) < 0.045, "employment_years"] = np.nan
    return frame
