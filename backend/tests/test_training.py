"""Scorecard development (split, select, fit, scale, evaluate), its metrics and the job queue."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from kivi_ui import jobs
from kivi_ui.analytics import binning, metrics
from kivi_ui.analytics.sample import FEATURES, simulate
from kivi_ui.analytics.training import (
    Candidate,
    TrainConfig,
    TrainingError,
    score_frame,
    split_rows,
    train,
)
from kivi_ui.db import get_sessionmaker
from kivi_ui.models import Job
from kivi_ui.routes.indicators import default_spec

# ---- Splitting ----------------------------------------------------------------------------------


def monthly_dates(rows: int, months: int) -> pd.Series:
    return pd.Series([f"2026-{m + 1:02d}-15" for m in np.arange(rows) * months // rows])


def test_split_holds_out_the_last_months_and_a_random_test_share():
    dates = monthly_dates(600, 6)
    config = TrainConfig(oot_months=2, test_ratio=0.25, seed=5)
    split, notes = split_rows(dates.index, dates, config)
    assert notes == []
    assert set(dates[split == "oot"].str[:7]) == {"2026-05", "2026-06"}
    assert set(dates[split != "oot"].str[:7]) == {f"2026-{m:02d}" for m in range(1, 5)}
    in_time = split[split != "oot"]
    assert len(in_time) == 400 and (in_time == "test").sum() == 100

    again, _ = split_rows(dates.index, dates, config)
    assert again.equals(split)
    other, _ = split_rows(dates.index, dates, config.model_copy(update={"seed": 6}))
    assert not other.equals(split) and (other == "test").sum() == 100
    assert other[split == "oot"].eq("oot").all()  # the seed only moves the in-time test rows


def test_split_without_usable_dates():
    index = pd.RangeIndex(200)
    split, notes = split_rows(index, None, TrainConfig(test_ratio=0.3))
    assert notes == ["no_date_for_oot"]
    assert (split == "oot").sum() == 0 and (split == "test").sum() == 60

    dates = monthly_dates(200, 3)
    split, notes = split_rows(index, dates, TrainConfig(oot_months=3))
    assert notes == ["too_few_months_for_oot"] and (split == "oot").sum() == 0

    split, notes = split_rows(index, None, TrainConfig(oot_months=0, test_ratio=0))
    assert notes == [] and (split == "train").all()


# ---- Training on the simulated retail sample ------------------------------------------------------

DEFAULT = TrainConfig()
# Tight limits so that every selection rule removes something.
STRICT = TrainConfig(max_features=8, vif_max=1.1, p_max=0.001)


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    return simulate(date(2026, 11, 19))


@pytest.fixture(scope="module")
def candidates() -> list[Candidate]:
    return [
        Candidate(f.name, f.name, f.zh, f.en, f.name, f.kind, f.unit, default_spec(f.kind).model_dump())
        for f in FEATURES
    ]


@pytest.fixture(scope="module")
def trained(sample, candidates) -> dict[str, dict]:
    return {
        name: train(sample, sample.target, sample.applied_on, candidates, config)
        for name, config in (("default", DEFAULT), ("strict", STRICT))
    }


CONFIGS = pytest.mark.parametrize(("name", "config"), [("default", DEFAULT), ("strict", STRICT)])


@CONFIGS
def test_selected_features_respect_the_limits(trained, name, config):
    result = trained[name]
    features = result["features"]
    assert 1 <= len(features) <= config.max_features
    assert all(f["coefficient"] > 0 for f in features)  # require_positive
    assert len(features) == 1 or all(f["p_value"] <= config.p_max for f in features)
    assert all(f["vif"] <= config.vif_max for f in features)
    assert all(f["iv"] >= config.iv_min for f in features)
    ivs = [f["iv"] for f in features]
    assert ivs == sorted(ivs, reverse=True)
    for f in features:
        assert f["bins"] and all(isinstance(b["points"], int) for b in f["bins"])
        assert set(f["psi"]) == {"test", "oot"} and all(v >= 0 for v in f["psi"].values())
        assert f["std_err"] > 0 and f["rule"]["kind"] == f["kind"]


@CONFIGS
def test_selection_steps_explain_every_dropped_candidate(trained, name, config):
    selection = trained[name]["selection"]
    screening = {c["code"]: c for c in selection["candidates"]}
    assert set(screening) == {f.name for f in FEATURES}
    kept = {f["code"] for f in trained[name]["features"]}
    assert kept == {code for code, c in screening.items() if c["selected"]}
    steps = {s["feature"]: s for s in selection["steps"]}
    assert len(steps) == len(selection["steps"])  # each candidate is dropped at most once
    assert set(steps) == set(screening) - kept
    for code, step in steps.items():
        assert screening[code]["reason"] == step["rule"] in ("iv", "max_features", "vif", "sign", "pvalue")
        if step["rule"] == "iv":
            assert step["value"] < config.iv_min
        elif step["rule"] == "vif":
            assert step["value"] > config.vif_max
        elif step["rule"] == "sign":
            assert step["value"] <= 0
        elif step["rule"] == "pvalue":
            assert step["value"] > config.p_max


def test_each_selection_rule_is_exercised(trained):
    rules = {name: {s["rule"] for s in result["selection"]["steps"]} for name, result in trained.items()}
    assert rules["default"] >= {"iv", "sign"}
    assert rules["strict"] >= {"iv", "max_features", "vif", "pvalue"}


@CONFIGS
def test_evaluation_per_split(trained, sample, name, config):
    result = trained[name]
    evaluation = result["evaluation"]
    assert set(evaluation) == {"train", "test", "oot"} and result["focus"] == "oot"
    assert result["notes"] == []
    assert sum(e["rows"] for e in evaluation.values()) == len(sample)
    assert evaluation["oot"]["period"] == ["2026-09", "2026-11"]
    assert evaluation["train"]["period"][1] == evaluation["test"]["period"][1] == "2026-08"
    in_time = evaluation["train"]["rows"] + evaluation["test"]["rows"]
    assert evaluation["test"]["rows"] == round(in_time * config.test_ratio)
    for split, entry in evaluation.items():
        assert 0.6 < entry["roc"]["auc"] < 0.9, split
        assert 0 < entry["roc"]["ks"] < 1
        assert entry["roc"]["gini"] == pytest.approx(2 * entry["roc"]["auc"] - 1, abs=2e-4)
        assert entry["bad_rate"] == pytest.approx(entry["bad"] / entry["rows"], abs=1e-6)
        assert sum(b["share"] for b in entry["bands"]) == pytest.approx(1, abs=1e-3)
        assert sum(b["count"] for b in entry["bands"]) == entry["rows"]
        assert len(entry["bands"]) == len(result["band_cuts"]) + 1
        assert ("psi" in entry) == (split != "train")
    assert result["band_cuts"] == sorted(result["band_cuts"])
    assert result["scale"] == {
        "base_score": 600,
        "base_odds": 20,
        "pdo": 50,
        "factor": pytest.approx(50 / np.log(2), abs=1e-5),
        "offset": pytest.approx(600 - 50 / np.log(2) * np.log(20), abs=1e-5),
    }
    assert result["fit"]["rows"] == evaluation["train"]["rows"]


@CONFIGS
def test_scoring_reproduces_the_training_scores(trained, sample, name, config):
    result = trained[name]
    scored = score_frame(result, sample)
    assert scored.columns.tolist() == ["score", "probability"] and scored.index.equals(sample.index)
    assert scored.probability.between(0, 1).all()
    ordered = scored.sort_values(["probability", "score"], ascending=[True, False])
    assert (np.diff(ordered.score) <= 0).all()  # riskier, lower score

    split, _ = split_rows(sample.index, sample.applied_on, config)
    for name_, entry in result["evaluation"].items():
        idx = split.index[split == name_]
        assert metrics.bands(scored.score[idx], sample.target[idx], result["band_cuts"]) == entry["bands"]
    focus = split.index[split == result["focus"]]
    assert metrics.gains(scored.score[focus], sample.target[focus]) == result["gains"]
    train_idx = split.index[split == "train"]
    stats = result["score_stats"]
    assert (stats["min"], stats["max"]) == (scored.score.min(), scored.score.max())
    assert stats["mean"] == pytest.approx(scored.score[train_idx].mean(), abs=0.05)

    # The scorecard: one row's points over its bins add up to its score.
    points = pd.Series(0, index=sample.index)
    for feature in result["features"]:
        rule = binning.Rule.from_dict(feature["rule"])
        groups = rule.assign(sample[feature["column"]])
        by_code = {b["code"]: b["points"] for b in feature["bins"]}
        assert groups.isin(list(by_code)).all(), feature["code"]
        points += groups.map(by_code).astype(int)
    tolerance = 0.5 * len(result["features"]) + 1  # each bin's points are rounded
    assert (points - scored.score).abs().max() <= tolerance


def test_a_high_iv_floor_leaves_no_features(sample, candidates):
    with pytest.raises(TrainingError) as error:
        train(sample, sample.target, sample.applied_on, candidates, TrainConfig(iv_min=0.5))
    assert error.value.code == "no_features_left"


def test_a_tiny_sample_has_too_few_events(sample, candidates):
    tiny = sample.head(300)
    with pytest.raises(TrainingError) as error:
        train(tiny, tiny.target, tiny.applied_on, candidates, TrainConfig())
    assert error.value.code == "too_few_events"
    assert error.value.detail["bad"] < 20 and error.value.detail["rows"] < 300


def test_failed_binning_is_screened_out(sample, candidates):
    frame = sample.assign(constant=1.0)
    broken = Candidate("x", "constant", "常数", None, "constant", "numeric", None, {"method": "monotonic"})
    chosen = [c for c in candidates if c.code in ("overdue_24m", "debt_ratio")] + [broken]
    result = train(frame, frame.target, frame.applied_on, chosen, TrainConfig())
    screening = {c["code"]: c for c in result["selection"]["candidates"]}
    assert screening["constant"]["selected"] is False
    assert screening["constant"]["reason"] in ("binning_failed", "iv")
    assert {f["code"] for f in result["features"]} == {"overdue_24m", "debt_ratio"}


# ---- Metrics --------------------------------------------------------------------------------------


def odds_probability(odds: float) -> np.ndarray:
    """Probability of the event at the given good:bad odds."""
    return np.array([1 / (1 + odds)])


def test_pdo_scale():
    factor, offset = metrics.pdo_scale(600, 20, 50)
    assert factor == pytest.approx(50 / np.log(2))
    assert offset + factor * np.log(20) == pytest.approx(600)
    assert metrics.to_score(odds_probability(20), factor, offset)[0] == 600
    assert metrics.to_score(odds_probability(40), factor, offset)[0] == 650
    assert metrics.to_score(odds_probability(10), factor, offset)[0] == 550
    # Extreme probabilities are clipped rather than producing infinite scores.
    assert np.isfinite(metrics.to_score(np.array([0.0, 1.0]), factor, offset)).all()


def test_gains_and_bands():
    rng = np.random.default_rng(1)
    score = pd.Series(rng.integers(300, 800, 1000))
    target = pd.Series((rng.random(1000) < (800 - score) / 1000).astype(int))
    rows = metrics.gains(score, target)
    assert [r["decile"] for r in rows] == list(range(1, 11)) and sum(r["count"] for r in rows) == 1000
    assert rows[-1]["cum_bad_pct"] == rows[-1]["cum_good_pct"] == 1.0
    cumulative = [r["cum_bad_pct"] for r in rows]
    assert cumulative == sorted(cumulative)
    assert rows[0]["bad_rate"] > rows[-1]["bad_rate"] and rows[0]["lift"] > 1  # lowest scores first
    assert sum(r["bad"] for r in rows) == target.sum()

    cuts = metrics.band_edges(score)
    assert cuts == sorted(set(cuts)) and len(cuts) == 9
    bands = metrics.bands(score, target, cuts)
    assert sum(b["count"] for b in bands) == 1000 and sum(b["share"] for b in bands) == pytest.approx(1)
    assert bands[0]["lower"] is None and bands[-1]["upper"] is None
    assert metrics.psi(metrics.band_codes(score, cuts), metrics.band_codes(score, cuts)) == pytest.approx(0)


# ---- Job queue ------------------------------------------------------------------------------------


@pytest.fixture
def registry(monkeypatch):
    """Register throwaway handlers that are removed again after the test."""

    def register(kind, fn, failure=None):
        monkeypatch.setitem(jobs.HANDLERS, kind, fn)
        if failure:
            monkeypatch.setitem(jobs.FAILURE_HOOKS, kind, failure)

    return register


def queue(db, kind: str, **params) -> Job:
    job = jobs.enqueue(db, kind, params, None)
    db.commit()
    return job


def fetch(db, job: Job) -> Job:
    db.expire_all()
    return db.get(Job, job.id)


def test_a_queued_job_runs_once(db, registry):
    calls = []

    def echo(session, job):
        calls.append(job.id)
        return {"echo": job.params["value"] * 2}

    registry("test_echo", echo)
    job = queue(db, "test_echo", value=21)
    assert job.status == "queued" and job.progress == 0
    assert jobs.run_pending() == 1
    assert jobs.run_pending() == 0
    done = fetch(db, job)
    assert calls == [job.id]
    assert (done.status, done.result, done.progress, done.error) == ("done", {"echo": 42}, 1.0, None)
    assert done.started_at is not None and done.finished_at >= done.started_at


def test_failures_are_recorded_and_hooked(db, registry):
    hooked = []

    def refuse(session, job):
        job.result = {"partial": True}  # rolled back with the failure
        raise jobs.JobFailed("no_data: nothing to do")

    def crash(session, job):
        raise ValueError("boom")

    registry("test_refuse", refuse, failure=lambda session, job: hooked.append((job.id, job.error)))
    registry("test_crash", crash)
    refused, crashed, unknown = queue(db, "test_refuse"), queue(db, "test_crash"), queue(db, "test_nope")
    assert jobs.run_pending() == 3

    refused = fetch(db, refused)
    assert (refused.status, refused.error, refused.result) == ("failed", "no_data: nothing to do", {})
    assert refused.finished_at is not None
    assert hooked == [(refused.id, "no_data: nothing to do")]
    crashed = fetch(db, crashed)
    assert (crashed.status, crashed.error) == ("failed", "ValueError: boom")
    unknown = fetch(db, unknown)
    assert unknown.status == "failed" and unknown.error == "No handler for job kind 'test_nope'"


def test_jobs_run_in_order_and_are_never_claimed_twice(db, registry):
    calls = []
    registry("test_count", lambda session, job: calls.append(job.params["n"]) or {})
    first, second = queue(db, "test_count", n=1), queue(db, "test_count", n=2)
    assert jobs.run_one() == first.id
    assert jobs.run_one() == second.id
    assert jobs.run_one() is None
    assert calls == [1, 2]

    # A row locked by another worker is skipped rather than waited for.
    third = queue(db, "test_count", n=3)
    with get_sessionmaker()() as other:
        other.execute(text("SELECT id FROM jobs WHERE id = :id FOR UPDATE"), {"id": third.id})
        assert jobs.run_one() is None
    assert jobs.run_one() == third.id
    assert calls == [1, 2, 3]


def test_stale_running_jobs_are_requeued(db, registry):
    registry("test_noop", lambda session, job: {})
    stale, fresh = queue(db, "test_noop"), queue(db, "test_noop")
    db.execute(
        text("UPDATE jobs SET status = 'running', started_at = now() - interval '2 hours' WHERE id = :id"),
        {"id": stale.id},
    )
    db.execute(
        text("UPDATE jobs SET status = 'running', started_at = now() WHERE id = :id"), {"id": fresh.id}
    )
    db.commit()
    jobs.requeue_stale(minutes=30)
    assert (fetch(db, stale).status, fetch(db, stale).started_at) == ("queued", None)
    assert fetch(db, fresh).status == "running"
    assert jobs.run_pending() == 1 and fetch(db, stale).status == "done"
