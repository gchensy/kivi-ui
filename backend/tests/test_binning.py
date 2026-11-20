import json

import numpy as np
import pandas as pd
import pytest
from kivi.binning import bin_edges
from kivi.woe import woe_table
from pydantic import ValidationError

from kivi_ui.analytics.binning import (
    NUMERIC_METHODS,
    BinningError,
    BinSpec,
    Rule,
    fit,
    iv_level,
    psi,
    psi_table_value,
    report,
)

ROWS = 3000


@pytest.fixture(scope="module")
def sample() -> tuple[pd.Series, pd.Series]:
    """A numeric feature whose bad rate rises with its value, with 5% missing."""
    rng = np.random.default_rng(11)
    risk = rng.normal(size=ROWS)
    target = pd.Series((rng.random(ROWS) < 1 / (1 + np.exp(1.5 - 1.2 * risk))).astype(int))
    values = pd.Series(np.round(50 + 10 * risk + rng.normal(0, 4, ROWS), 1))
    values[rng.random(ROWS) < 0.05] = np.nan
    return values, target


@pytest.fixture(scope="module")
def levels() -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(5)
    values = pd.Series(rng.choice(list("abcde"), ROWS, p=[0.5, 0.3, 0.16, 0.03, 0.01]), dtype=object)
    target = pd.Series((rng.random(ROWS) < np.where(values == "a", 0.1, 0.3)).astype(int))
    values[rng.random(ROWS) < 0.04] = None
    return values, target


def intervals(result: dict) -> list[dict]:
    return [b for b in result["bins"] if b["kind"] == "interval"]


@pytest.mark.parametrize("method", NUMERIC_METHODS)
def test_every_numeric_method_bins_all_rows(sample, method):
    values, target = sample
    spec = BinSpec(method=method, bins=5, cuts=[40, 50, 60] if method == "manual" else [])
    rule, _ = fit(values, target, spec, "numeric")
    result = report(rule, values, target)

    assert rule.kind == "numeric" and rule.cuts == sorted(rule.cuts)
    assert 2 <= len(intervals(result)) <= 5
    assert sum(b["count"] for b in result["bins"]) == result["rows"] == ROWS
    assert sum(b["share"] for b in result["bins"]) == pytest.approx(1, abs=1e-5)
    assert all(b["bad"] + b["good"] == b["count"] for b in result["bins"])
    assert [b["count"] for b in result["bins"] if b["kind"] == "missing"] == [values.isna().sum()]
    assert result["missing_rate"] == pytest.approx(values.isna().mean(), abs=1e-6)
    # Intervals are contiguous and open-ended.
    bounds = [(b["lower"], b["upper"]) for b in intervals(result)]
    assert bounds[0][0] is None and bounds[-1][1] is None
    assert all(left[1] == right[0] for left, right in zip(bounds, bounds[1:], strict=False))
    assert result["iv"] > 0.1 and result["level"] == iv_level(result["iv"])
    json.dumps(result, allow_nan=False)


def test_monotonic_trend_follows_the_data(sample):
    values, target = sample
    rule, _ = fit(values, target, BinSpec(method="monotonic", bins=6), "numeric")
    rising = report(rule, values, target)
    assert rising["trend"] == "increasing"
    rates = [b["bad_rate"] for b in intervals(rising)]
    assert rates == sorted(rates)

    flipped = -values
    rule, _ = fit(flipped, target, BinSpec(method="monotonic", bins=6), "numeric")
    falling = report(rule, flipped, target)
    assert falling["trend"] == "decreasing"
    assert len(intervals(falling)) >= 2


def test_information_value_matches_kivi(sample):
    values, target = sample
    rule, _ = fit(values, target, BinSpec(method="quantile", bins=5), "numeric")
    result = report(rule, values, target)
    assert result["iv"] == pytest.approx(sum(b["iv"] for b in result["bins"]), abs=1e-9)

    groups = pd.cut(values, bin_edges(values.dropna(), 5), labels=False).fillna(-1)
    expected = woe_table(groups, target).loc[[0, 1, 2, 3, 4, -1]]  # intervals, then missing
    assert result["iv"] == pytest.approx(expected.iv.sum(), abs=1e-4)
    assert [b["count"] for b in result["bins"]] == list(expected.event + expected.non_event)
    assert [b["woe"] for b in result["bins"]] == pytest.approx(list(expected.woe), abs=1e-5)


def test_special_values_and_missing_get_their_own_bins(sample):
    values, target = sample
    coded = values.copy()
    coded[::20] = -1
    coded[7::50] = -99
    spec = BinSpec(method="quantile", bins=4, special=[-1, -99, -1])
    assert spec.special == [-99, -1]
    rule, _ = fit(coded, target, spec, "numeric")
    result = report(rule, coded, target)

    special = [b for b in result["bins"] if b["kind"] == "special"]
    assert [(b["code"], b["value"]) for b in special] == [("s0", -99), ("s1", -1)]
    assert [b["count"] for b in special] == [(coded == -99).sum(), (coded == -1).sum()]
    assert result["bins"][:2] == special  # special bins come first, missing last
    assert result["bins"][-1]["kind"] == "missing"
    assert result["bins"][-1]["count"] == coded.isna().sum()
    # Codes are left out of the fit: every cut lies inside the observed range.
    observed = coded[~coded.isin([-1, -99])].dropna()
    assert observed.min() < min(rule.cuts) and len(intervals(result)) == 4
    assert sum(b["count"] for b in result["bins"]) == ROWS


def test_manual_cuts_give_exactly_one_more_interval(sample):
    values, target = sample
    spec = BinSpec(method="manual", cuts=[60, 40, 50, 50, float("inf")])
    assert spec.cuts == [40, 50, 60]
    rule, notes = fit(values, target, spec, "numeric")
    assert rule.cuts == [40, 50, 60] and notes == []
    bounds = [(b["lower"], b["upper"]) for b in intervals(report(rule, values, target))]
    assert bounds == [(None, 40), (40, 50), (50, 60), (60, None)]
    assert rule.assign(pd.Series([40, 40.1, 1e9, None])).tolist() == ["b0", "b1", "b3", "missing"]
    with pytest.raises(ValidationError):
        BinSpec(method="manual", cuts=[])


def test_category_binning_merges_rare_levels(levels):
    values, target = levels
    rule, _ = fit(values, target, BinSpec(method="category", min_bin_share=0.05), "category")
    assert rule.kind == "category"
    assert rule.levels == {"a": "c:a", "b": "c:b", "c": "c:c", "d": "other", "e": "other"}

    result = report(rule, values, target)
    assert [b["code"] for b in result["bins"]] == ["c:a", "c:b", "c:c", "other", "missing"]
    assert [b.get("value") for b in result["bins"][:3]] == ["a", "b", "c"]
    other = next(b for b in result["bins"] if b["code"] == "other")
    assert other["count"] == values.isin(["d", "e"]).sum()
    assert result["trend"] == "unordered" and result["rows"] == ROWS

    unseen = rule.assign(pd.Series(["a", "zzz", None, "e"], dtype=object))
    assert unseen.tolist() == ["c:a", "other", "missing", "other"]


def test_category_binning_keeps_two_levels_and_limits_cardinality(levels):
    values, target = levels
    rule, _ = fit(values, target, BinSpec(method="category", min_bin_share=0.5), "category")
    assert sorted(code for code in rule.levels.values() if code != "other") == ["c:a", "c:b"]

    many = pd.Series([f"v{i % 61}" for i in range(ROWS)])
    with pytest.raises(BinningError) as error:
        fit(many, target, BinSpec(method="category"), "category")
    assert error.value.code == "too_many_categories" and error.value.detail["limit"] == 60


def test_rule_round_trips_through_json(sample, levels):
    values, target = sample
    coded = values.where(values.index % 25 != 0, -1)
    numeric, _ = fit(coded, target, BinSpec(method="tree", special=[-1]), "numeric")
    category, _ = fit(*levels, BinSpec(method="category"), "category")
    for rule, data in ((numeric, coded), (category, levels[0])):
        again = Rule.from_dict(json.loads(json.dumps(rule.to_dict())))
        assert again == rule
        pd.testing.assert_series_equal(again.assign(data), rule.assign(data))


def test_psi_of_a_sample_against_itself_is_zero(sample, levels):
    values, target = sample
    rule, _ = fit(values, target, BinSpec(method="quantile"), "numeric")
    assert psi(rule, values, values) == pytest.approx(0, abs=1e-12)
    assert psi(rule, values, values.sample(frac=1, random_state=1)) == pytest.approx(0, abs=1e-12)
    assert psi(rule, values, values + 8) > 0.25

    category, _ = fit(*levels, BinSpec(method="category"), "category")
    groups = category.assign(levels[0])
    assert psi_table_value(groups, groups) == pytest.approx(0, abs=1e-12)
    assert psi_table_value(groups[:1000], groups[1000:]) < 0.05


def test_order_and_describe():
    rule = Rule("numeric", cuts=[1.5, 3.0], special=[-1.0])
    codes = ["missing", "b1", "s0", "b10", "b0", "other", "b2"]
    assert rule.order(codes) == ["s0", "b0", "b1", "b2", "b10", "other", "missing"]
    assert rule.describe("b0") == {"kind": "interval", "lower": None, "upper": 1.5}
    assert rule.describe("b2") == {"kind": "interval", "lower": 3.0, "upper": None}
    assert rule.describe("s0") == {"kind": "special", "value": -1.0}
    assert rule.describe("c:x") == {"kind": "category", "value": "x"}
    assert [iv_level(v) for v in (0.01, 0.05, 0.2, 0.4, 0.6)] == [
        "useless",
        "weak",
        "medium",
        "strong",
        "suspicious",
    ]


def test_unusable_inputs_raise_binning_errors(sample):
    values, target = sample
    with pytest.raises(BinningError) as error:
        fit(pd.Series([np.nan] * 10), target[:10], BinSpec(), "numeric")
    assert error.value.code == "no_observations"
    with pytest.raises(BinningError) as error:
        fit(pd.Series([-1.0] * 10), target[:10], BinSpec(special=[-1]), "numeric")
    assert error.value.code == "no_observations"
    with pytest.raises(BinningError) as error:
        fit(values, pd.Series(0, index=values.index), BinSpec(method="chimerge"), "numeric")
    assert error.value.code == "binning_failed"
