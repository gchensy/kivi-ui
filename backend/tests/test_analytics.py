import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from kivi.binning import bin_edges
from kivi.woe import woe_table

from kivi_ui.analytics.sample import FEATURES, simulate
from kivi_ui.analytics.scorecard import TRAIN_MONTHS, build

AS_OF = date(2026, 11, 19)


@pytest.fixture(scope="module")
def sample():
    return simulate(AS_OF)


@pytest.fixture(scope="module")
def payload(sample):
    return build(sample, AS_OF)


def test_sample_is_reproducible_and_dated(sample):
    again = simulate(AS_OF)
    pd.testing.assert_frame_equal(sample, again)
    assert sample.applied_on.max().date() <= AS_OF
    assert sample.month.nunique() == 12 and sample.month.max() == "2026-11"
    assert 0.03 < sample.target.mean() < 0.08


def test_payload_is_json(payload):
    text = json.dumps(payload, allow_nan=False)
    assert len(text) < 200_000


def test_information_value_matches_kivi(sample, payload):
    train = sample[sample.month_index < TRAIN_MONTHS]
    by_name = {s["name"]: s for s in payload["indicators"]}
    values = train["debt_ratio"]
    groups = pd.cut(values, bin_edges(values, 5), labels=False).fillna(-1)
    expected = woe_table(groups, train.target).iv.sum()
    assert by_name["debt_ratio"]["iv"] == pytest.approx(expected, abs=1e-4)
    for summary in payload["indicators"]:
        assert sum(b["count"] for b in summary["bins"]) == len(train)
        assert sum(b["iv"] for b in summary["bins"]) == pytest.approx(summary["iv"], abs=1e-3)
    assert [s["iv"] for s in payload["indicators"]] == sorted(
        (s["iv"] for s in payload["indicators"]), reverse=True
    )
    assert len(payload["indicators"]) == len(FEATURES)


def test_scorecard_is_sensible(payload):
    model = payload["model"]
    assert 2 <= len(model["features"]) <= 8
    assert all(card["coefficient"] > 0 for card in model["scorecard"])  # WOE rises with risk
    assert 0.65 < model["roc"]["oot"]["auc"] < 0.9
    assert model["roc"]["train"]["curve"][0] == {"fpr": 0.0, "tpr": 0.0}
    for split in ("train", "oot"):
        assert sum(b["share"] for b in model["bands"][split]) == pytest.approx(1, abs=1e-3)
    gains = model["gains"]
    assert gains[-1]["cum_bad_pct"] == pytest.approx(1)
    assert gains[0]["bad_rate"] > gains[-1]["bad_rate"]  # riskiest decile first


def test_drift_is_detected_in_recent_months(payload):
    monthly = payload["stability"]["monthly"]
    reference = [m["score_psi"] for m in monthly if m["in_reference"]]
    assert max(reference) < 0.05
    assert monthly[-1]["score_psi"] > 0.1
    flagged = {a["subject"] for a in payload["alerts"] if a["kind"] == "feature_psi"}
    assert {"channel", "inquiries_6m"} <= flagged
    assert [a["id"] for a in payload["alerts"]] == [
        f"AL{i:03d}" for i in range(1, len(payload["alerts"]) + 1)
    ]


def test_decisions_cover_last_thirty_days(payload):
    daily = payload["decisions"]["daily"]
    assert len(daily) == 30 and daily[-1]["date"] == AS_OF.isoformat()
    total = sum(d["total"] for d in daily)
    assert total == payload["kpis"]["applications_30d"]
    assert all(d["pass"] + d["review"] + d["reject"] == d["total"] for d in daily)
    effect = payload["decisions"]["effect"]
    assert effect["pass"] < effect["review"] < effect["reject"]
    assert np.isclose(payload["kpis"]["approval_rate_30d"], sum(d["pass"] for d in daily) / total, atol=1e-4)


def test_analytics_endpoint_requires_sign_in(anon, make_user, login):
    assert anon.get("/api/v1/analytics/demo").status_code == 401
    make_user("ana")
    body = login("ana").get("/api/v1/analytics/demo").json()
    assert set(body) >= {"kpis", "indicators", "model", "stability", "alerts", "decisions"}
    assert login("ana").post("/api/v1/analytics/demo/rebuild").status_code == 403
