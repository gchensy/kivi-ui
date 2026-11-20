"""Monitors and their checks, runs and alerts; scheduling; the overview and stability views."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from conftest import loan_frame, upload
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from kivi_ui import jobs
from kivi_ui.analytics import binning, metrics
from kivi_ui.analytics.training import score_frame
from kivi_ui.data import store
from kivi_ui.demo import (
    MODEL_CODE,
    STRATEGY_CODE,
    refresh,
    seed_datasets,
    seed_model,
    seed_monitors,
    seed_strategy,
)
from kivi_ui.models import (
    Alert,
    AuditLog,
    Dataset,
    DecisionLog,
    ModelVersion,
    Monitor,
    MonitorRun,
    RiskModel,
    Role,
    Strategy,
    StrategyVersion,
    User,
)
from kivi_ui.monitoring import checks
from kivi_ui.monitoring.checks import DEFAULT_THRESHOLDS, CheckError
from kivi_ui.monitoring.schedule import next_run
from kivi_ui.monitoring.service import due_monitors, run_monitor, schedule_due

API = "/api/v1"
MISSING = "00000000-0000-0000-0000-000000000000"
FEATURES = ["income", "city", "年龄", "responded"]
MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 20, 4, 0, tzinfo=UTC)  # noon in Shanghai


class Sessions:
    """Signed-in clients by username, each created on first use."""

    def __init__(self, login):
        self._login = login

    def __getattr__(self, name: str) -> TestClient:
        client = self._login(name)
        setattr(self, name, client)
        return client


@pytest.fixture
def users(make_user, login) -> Sessions:
    """Two analysts (ana usually owns things) and an administrator."""
    for name, role in (("ana", Role.analyst), ("bob", Role.analyst), ("root", Role.admin)):
        make_user(name, role)
    return Sessions(login)


# ---- Dated samples and a model --------------------------------------------------------------------


def csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode()


def drifting_frame() -> pd.DataFrame:
    """Six months of 100 loans. Income jumps by 8000 in June only and June's labels are shuffled,
    so in the last month the score distribution shifts and the model stops ranking."""
    frame = loan_frame(rows=600)
    month = frame.apply_date.str[:7]
    frame.loc[month == "2026-05", "income"] -= 8000  # loan_frame drifts May and June; keep June only
    june = month == "2026-06"
    frame.loc[june, "target"] = np.random.default_rng(0).permutation(frame.loc[june, "target"].to_numpy())
    return frame


@pytest.fixture
def model(users):
    """RETAIL_APP trained on the drifting sample (Jan-Mar in time, Apr-Jun out of time), online."""
    frame = drifting_frame()
    dataset = upload(users.ana, csv(frame), name="train").json()
    assert (dataset["date_column"], dataset["target_column"]) == ("apply_date", "target")
    indicators = users.ana.post(
        f"{API}/indicators/import", json={"dataset_id": dataset["id"], "columns": FEATURES}
    ).json()
    created = users.ana.post(f"{API}/models", json={"code": "retail_app", "name": "零售申请评分卡"}).json()
    body = {"dataset_id": dataset["id"], "indicator_ids": [i["id"] for i in indicators], "config": {}}
    version = users.ana.post(f"{API}/models/{created['id']}/versions", json=body).json()
    assert jobs.run_pending() == 1
    for c, action in ((users.ana, "submit"), (users.root, "approve"), (users.root, "online")):
        response = c.post(f"{API}/model-versions/{version['id']}/{action}", json={"comment": ""})
        assert response.status_code == 200, response.json()
    version = response.json()
    # 年龄 is stored as the positional column c8, so its indicator code is c8 too.
    assert [(f["code"], f["column"], f["header"]) for f in version["result"]["features"]] == [
        ("income", "income", "income"),
        ("c8", "c8", "年龄"),
    ]
    assert version["result"]["evaluation"]["train"]["period"] == ["2026-01", "2026-03"]
    return SimpleNamespace(
        frame=frame,
        dataset=dataset,
        indicators={i["code"]: i for i in indicators},
        model=created,
        version=version,
    )


def stored(db, dataset: dict, columns: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Columns of an uploaded dataset as the checks read them, and each row's month."""
    frame = store.read_columns(db, db.get(Dataset, uuid.UUID(dataset["id"])), [*columns, "apply_date"])
    return frame, pd.to_datetime(frame.apply_date).dt.strftime("%Y-%m")


def psi(groups: pd.Series, reference: pd.Series, part: pd.Series) -> float:
    return metrics.psi(groups[reference], groups[part])


# ---- Monitors through the API -------------------------------------------------------------------


def new_monitor(c, kind, name=None, **fields):
    return c.post(f"{API}/monitors", json={"name": name or kind, "kind": kind} | fields)


def create(c, kind, **fields) -> dict:
    response = new_monitor(c, kind, **fields)
    assert response.status_code == 201, response.json()
    return response.json()


def run(c, monitor) -> dict:
    """Run a monitor now; returns the new run with its detail."""
    response = c.post(f"{API}/monitors/{monitor['id']}/run")
    assert response.status_code == 200, response.json()
    newest = response.json()["runs"][0]
    return c.get(f"{API}/monitor-runs/{newest['id']}").json()


def failure(c, monitor) -> str:
    """Run a monitor that cannot run; returns the error code."""
    got = run(c, monitor)
    assert (got["status"], got["level"], got["value"]) == ("failed", "error", None), got
    assert got["code"] == got["detail"]["code"] and got["error"]
    return got["code"]


# ---- Strategies, decision logs, monitors and alerts in the database ------------------------------


def rule(code, field, op, value, decision="reject", **extra) -> dict:
    when = {"mode": "all", "items": [{"field": field, "op": op, "value": value}]}
    return {"code": code, "name": f"rule {code}", "decision": decision, "when": when} | extra


RULES = [
    rule("R01", "age", "lt", 22),
    rule("R02", "income", "lt", 3000),
    rule("V01", "income", "lt", 5000, decision="review"),
    rule("R09", "age", "gt", 70, enabled=False),
]


def make_strategy(db, code="RETAIL_APPLY", rules=None, status="online") -> Strategy:
    strategy = Strategy(code=code, name=f"策略 {code}", name_en=f"Strategy {code}")
    db.add(strategy)
    db.flush()
    definition = {"default_decision": "pass", "rules": RULES if rules is None else rules}
    db.add(StrategyVersion(strategy_id=strategy.id, version=1, status=status, definition=definition))
    db.commit()
    return strategy


def log(db, code, decision, at, *, hits=(), n=1, source="api") -> None:
    for _ in range(n):
        db.add(
            DecisionLog(
                request_id=uuid.uuid4().hex,
                strategy_code=code,
                version=1,
                decision=decision,
                hit_rules=list(hits),
                created_at=at,
                source=source,
            )
        )


def shifted_strategy(db, code="RETAIL_APPLY") -> Strategy:
    """An online strategy whose approval rate fell from 90% to 70% this week, as R01 hit more."""
    strategy = make_strategy(db, code)
    now = datetime.now(UTC)
    log(db, code, "pass", now - timedelta(days=1), n=35)
    log(db, code, "reject", now - timedelta(days=1), n=15, hits=["R01"])
    log(db, code, "pass", now - timedelta(days=10), n=90)
    log(db, code, "reject", now - timedelta(days=10), n=10, hits=["R01"])
    db.commit()
    return strategy


def make_monitor(db, kind, *, thresholds=None, params=None, schedule=None, **fields) -> Monitor:
    monitor = Monitor(
        name=fields.pop("name", kind),
        kind=kind,
        params=params or {},
        thresholds=thresholds or DEFAULT_THRESHOLDS[kind],
        schedule=schedule or {"freq": "daily", "hour": 6, "minute": 0, "weekday": 0},
        **fields,
    )
    db.add(monitor)
    db.commit()
    return monitor


def make_alert(db, monitor, status="open", level="warn", *, seen=None, **fields) -> Alert:
    seen = seen or datetime.now(UTC)
    alert = Alert(
        monitor_id=monitor.id,
        status=status,
        level=level,
        peak_level=level,
        value=0.2,
        threshold=DEFAULT_THRESHOLDS[monitor.kind][level],
        first_seen_at=seen - timedelta(hours=1),
        last_seen_at=seen,
        events=[],
        **fields,
    )
    db.add(alert)
    db.commit()
    return alert


# ---- Dataset checks -------------------------------------------------------------------------------


def test_score_psi_by_month_against_the_training_months(users, model, db):
    monitor = create(users.ana, "score_psi", model_id=model.model["id"])
    assert monitor["dataset"] == {"id": model.dataset["id"], "name": "train"}  # the training sample
    got = run(users.ana, monitor)
    assert (got["status"], got["trigger"], got["error"], got["code"]) == ("done", "manual", None, None)
    detail = got["detail"]
    assert detail["model"] == {"code": "RETAIL_APP", "version": 1, "version_id": model.version["id"]}
    assert (detail["reference"], detail["period"]) == (["2026-01", "2026-03"], "2026-06")
    series = detail["series"]
    assert [s["period"] for s in series] == MONTHS
    assert [s["in_reference"] for s in series] == [True, True, True, False, False, False]
    assert [s["rows"] for s in series] == [100] * 6

    result = model.version["result"]
    frame, month = stored(db, model.dataset, ["income", "c8", "target"])
    scored = score_frame(result, frame[["income", "c8"]])
    bands = metrics.band_codes(scored.score, result["band_cuts"])
    reference = month.isin(MONTHS[:3])
    for s in series:
        part = month == s["period"]
        assert s["value"] == pytest.approx(psi(bands, reference, part), abs=1e-6), s["period"]
        assert s["mean_score"] == pytest.approx(scored.score[part].mean(), abs=0.051)
        assert s["bad_rate"] == pytest.approx(frame.target[part].mean(), abs=1e-6)
    # The headline is the last month, where income jumped.
    assert got["value"] == series[-1]["value"] > 0.25 > max(s["value"] for s in series[:4])
    assert got["level"] == "alert"

    # An explicit reference period.
    url = f"{API}/monitors/{monitor['id']}"
    patched = users.ana.patch(url, json={"params": {"reference": {"start": "2026-02", "end": "2026-04"}}})
    assert patched.json()["params"]["reference"] == {"start": "2026-02", "end": "2026-04"}
    explicit = run(users.ana, monitor)["detail"]
    assert explicit["reference"] == ["2026-02", "2026-04"]
    assert [s["in_reference"] for s in explicit["series"]] == [False, True, True, True, False, False]
    reference = month.isin(MONTHS[1:4])
    for s in explicit["series"]:
        assert s["value"] == pytest.approx(psi(bands, reference, month == s["period"]), abs=1e-6)

    # The reference must hold data and end before the latest month.
    for start, end in (("2026-04", "2026-06"), ("2026-06", "2026-08"), ("2027-01", "2027-03")):
        users.ana.patch(url, json={"params": {"reference": {"start": start, "end": end}}})
        got = run(users.ana, monitor)
        assert got["detail"]["code"] == "bad_reference" and got["level"] == "error", (start, end)
    assert got["detail"] == {"code": "bad_reference", "start": "2027-01", "end": "2027-03"}
    assert got["error"] == "No data in the reference period"
    # A month that is not a month is rejected up front.
    for bad in ({"start": "2026-13", "end": "2026-14"}, {"start": "2026-04", "end": "2026-02"}):
        assert users.ana.patch(url, json={"params": {"reference": bad}}).status_code == 422


def test_score_psi_on_another_sample_uses_its_first_half(users, model, db):
    recent = model.frame[model.frame.apply_date >= "2026-03"]
    dataset = upload(users.ana, csv(recent), name="recent").json()
    monitor = create(users.ana, "score_psi", model_id=model.model["id"], dataset_id=dataset["id"])
    got = run(users.ana, monitor)
    detail = got["detail"]
    assert (detail["reference"], detail["period"]) == (["2026-03", "2026-04"], "2026-06")
    assert [(s["period"], s["in_reference"]) for s in detail["series"]] == [
        ("2026-03", True),
        ("2026-04", True),
        ("2026-05", False),
        ("2026-06", False),
    ]
    frame, month = stored(db, dataset, ["income", "c8"])
    result = model.version["result"]
    bands = metrics.band_codes(score_frame(result, frame[["income", "c8"]]).score, result["band_cuts"])
    reference = month.isin(["2026-03", "2026-04"])
    assert got["value"] == pytest.approx(psi(bands, reference, month == "2026-06"), abs=1e-6)

    # Without a target the bad rate is empty; without a date there are no months.
    users.ana.patch(f"{API}/datasets/{dataset['id']}", json={"clear": ["target_column"]})
    unlabelled = run(users.ana, monitor)
    assert unlabelled["status"] == "done" and unlabelled["value"] == got["value"]
    assert all(s["bad_rate"] is None for s in unlabelled["detail"]["series"])
    users.ana.patch(f"{API}/datasets/{dataset['id']}", json={"clear": ["date_column"]})
    assert failure(users.ana, monitor) == "no_date_column"


def test_model_ks_measures_the_relative_drop(users, model, db):
    monitor = create(users.ana, "model_ks", model_id=model.model["id"])
    assert monitor["thresholds"] == {"warn": 0.1, "alert": 0.2}
    got = run(users.ana, monitor)
    detail = got["detail"]
    assert (detail["reference"], detail["period"]) == (["2026-01", "2026-03"], "2026-06")

    frame, month = stored(db, model.dataset, ["income", "c8", "target"])
    probability = score_frame(model.version["result"], frame[["income", "c8"]]).probability.to_numpy()
    y = frame.target.astype(float)

    def roc(mask: pd.Series) -> dict:
        return metrics.roc(y[mask], probability[mask.to_numpy()])

    base = roc(month.isin(MONTHS[:3]))
    assert detail["reference_metrics"] == {"auc": base["auc"], "ks": base["ks"], "labelled": 300}
    for s in detail["series"]:
        r = roc(month == s["period"])
        assert (s["ks"], s["auc"], s["value"], s["labelled"]) == (r["ks"], r["auc"], r["ks"], 100)
        assert s["in_reference"] == (s["period"] in MONTHS[:3])
    june = roc(month == "2026-06")
    assert (detail["ks"], detail["auc"]) == (june["ks"], june["auc"])
    assert got["value"] == pytest.approx(1 - june["ks"] / base["ks"], abs=1e-6)
    assert got["value"] > 0.5 and got["level"] == "alert"  # shuffled labels: the KS collapsed


def test_model_ks_reports_the_latest_labelled_month(users, model, db):
    frame = model.frame.copy()
    frame.loc[frame.apply_date >= "2026-06", "target"] = np.nan
    dataset = upload(users.ana, csv(frame), name="unlabelled june").json()
    assert dataset["target_column"] == "target"
    monitor = create(users.ana, "model_ks", model_id=model.model["id"], dataset_id=dataset["id"])
    got = run(users.ana, monitor)
    detail = got["detail"]
    assert detail["period"] == "2026-05" and detail["reference"] == ["2026-01", "2026-03"]
    june = detail["series"][-1]
    assert (june["ks"], june["auc"], june["labelled"], june["bad_rate"]) == (None, None, 0, None)
    may = detail["series"][-2]
    assert got["value"] == pytest.approx(1 - may["ks"] / detail["reference_metrics"]["ks"], abs=1e-6)

    # No label after the reference period, or no target at all.
    frame.loc[frame.apply_date >= "2026-04", "target"] = np.nan
    late = upload(users.ana, csv(frame), name="unlabelled q2").json()
    users.ana.patch(f"{API}/monitors/{monitor['id']}", json={"dataset_id": late["id"]})
    assert failure(users.ana, monitor) == "no_labelled_months"
    users.ana.patch(f"{API}/datasets/{late['id']}", json={"clear": ["target_column"]})
    assert failure(users.ana, monitor) == "no_target"


def test_dataset_checks_fail_cleanly(users, model, db):
    url = f"{API}/datasets"
    lacking = upload(users.ana, csv(model.frame.drop(columns=["income"])), name="lacking").json()
    monitor = create(users.ana, "score_psi", model_id=model.model["id"], dataset_id=lacking["id"])
    got = run(users.ana, monitor)
    assert got["detail"] == {"code": "missing_columns", "columns": ["income"]}
    assert got["error"] == "The dataset lacks model inputs"

    one_month = upload(users.ana, csv(model.frame[model.frame.apply_date < "2026-02"]), name="jan").json()
    users.ana.patch(f"{API}/monitors/{monitor['id']}", json={"dataset_id": one_month["id"]})
    assert failure(users.ana, monitor) == "too_few_months"

    # A model without an online version.
    other = users.ana.post(f"{API}/models", json={"code": "other", "name": "其他"}).json()
    offline = create(users.ana, "score_psi", model_id=other["id"], dataset_id=model.dataset["id"])
    got = run(users.ana, offline)
    assert got["detail"] == {"code": "model_not_online", "model": "OTHER"}

    # The monitored dataset was deleted.
    copy = upload(users.ana, csv(model.frame), name="copy").json()
    ks = create(users.ana, "model_ks", model_id=model.model["id"], dataset_id=copy["id"])
    assert users.ana.delete(f"{url}/{copy['id']}").status_code == 204
    assert users.ana.get(f"{API}/monitors/{ks['id']}").json()["dataset"] is None
    assert failure(users.ana, ks) == "dataset_required"

    # Failed runs are recorded and listed but never become the latest result.
    detail = users.ana.get(f"{API}/monitors/{ks['id']}").json()
    assert detail["latest"] is None and detail["last_level"] == "error" and detail["last_value"] is None
    assert [r["status"] for r in detail["runs"]] == ["failed"] and detail["alert"] is None


def test_indicator_psi_on_the_model_inputs(users, model, db):
    monitor = create(users.ana, "indicator_psi", model_id=model.model["id"])
    assert monitor["dataset"]["id"] == model.dataset["id"] and monitor["thresholds"] == {
        "warn": 0.1,
        "alert": 0.25,
    }
    got = run(users.ana, monitor)
    detail = got["detail"]
    assert (detail["reference"], detail["period"], detail["skipped"]) == (
        ["2026-01", "2026-03"],
        "2026-06",
        [],
    )
    frame, month = stored(db, model.dataset, ["income", "c8"])
    reference = month.isin(MONTHS[:3])
    expected = {}
    for f in model.version["result"]["features"]:
        groups = binning.Rule.from_dict(f["rule"]).assign(frame[f["column"]])
        expected[f["code"]] = [binning.psi_table_value(groups[reference], groups[month == m]) for m in MONTHS]
    rows = detail["indicators"]
    assert [r["code"] for r in rows] == ["income", "c8"]  # the worst first
    assert (rows[1]["name"], rows[1]["name_en"]) == ("年龄", None)
    for r in rows:
        assert r["values"] == pytest.approx(expected[r["code"]], abs=1e-6)
        assert r["latest"] == r["values"][-1]
    assert detail["worst"] == {
        "code": "income",
        "name": "income",
        "name_en": None,
        "value": rows[0]["latest"],
    }
    assert got["value"] == rows[0]["latest"] > 0.25 and got["level"] == "alert"
    assert [s["value"] for s in detail["series"]] == pytest.approx(
        [max(a, b) for a, b in zip(expected["income"], expected["c8"], strict=True)], abs=1e-6
    )
    assert [s["in_reference"] for s in detail["series"]] == [True, True, True, False, False, False]

    # A model input the sample lacks is skipped, the others are still checked.
    lacking = upload(users.ana, csv(model.frame.drop(columns=["年龄"])), name="no age").json()
    users.ana.patch(f"{API}/monitors/{monitor['id']}", json={"dataset_id": lacking["id"]})
    detail = run(users.ana, monitor)["detail"]
    assert detail["skipped"] == [{"code": "c8", "name": "年龄", "name_en": None, "reason": "missing_column"}]
    assert [r["code"] for r in detail["indicators"]] == ["income"]
    assert detail["reference"] == ["2026-01", "2026-03"]  # not the training sample: its first half


def test_indicator_psi_on_chosen_indicators(users, model, db):
    ana = users.ana
    [outcome] = ana.post(
        f"{API}/indicators/import", json={"dataset_id": model.dataset["id"], "columns": ["outcome"]}
    ).json()
    responded = model.indicators["responded"]
    after = ana.delete(f"{API}/indicators/{responded['id']}/schemes/{responded['default_scheme']['id']}")
    assert after.json()["default_scheme"] is None
    recent = model.frame[model.frame.apply_date >= "2026-03"].drop(columns=["outcome"])
    dataset = upload(ana, csv(recent), name="recent").json()
    chosen = [model.indicators[c]["id"] for c in ("income", "city", "responded")] + [outcome["id"]]
    monitor = create(ana, "indicator_psi", dataset_id=dataset["id"], params={"indicator_ids": chosen})
    assert monitor["model"] is None and monitor["params"]["indicator_ids"] == chosen

    got = run(ana, monitor)
    detail = got["detail"]
    assert detail["skipped"] == [
        {"code": "outcome", "name": "outcome", "name_en": None, "reason": "missing_column"},
        {"code": "responded", "name": "responded", "name_en": None, "reason": "no_scheme"},
    ]
    assert detail["reference"] == ["2026-03", "2026-04"] and detail["period"] == "2026-06"
    frame, month = stored(db, dataset, ["income", "city"])
    reference = month.isin(["2026-03", "2026-04"])
    expected = {}
    for code in ("income", "city"):
        indicator = ana.get(f"{API}/indicators/{model.indicators[code]['id']}").json()
        [scheme] = [s for s in indicator["schemes"] if s["id"] == indicator["default_scheme"]["id"]]
        groups = binning.Rule.from_dict(scheme["rule"]).assign(frame[code])
        expected[code] = [
            binning.psi_table_value(groups[reference], groups[month == m]) for m in sorted(set(month))
        ]
    rows = {r["code"]: r for r in detail["indicators"]}
    assert [r["code"] for r in detail["indicators"]] == ["income", "city"]
    for code, values in expected.items():
        assert rows[code]["values"] == pytest.approx(values, abs=1e-6), code
    assert detail["worst"]["code"] == "income" and got["value"] == rows["income"]["latest"]

    # When nothing can be checked the run fails and says why.
    only = [responded["id"], outcome["id"]]
    ana.patch(f"{API}/monitors/{monitor['id']}", json={"params": {"indicator_ids": only}})
    got = run(ana, monitor)
    assert got["detail"]["code"] == "no_indicators"
    assert [s["reason"] for s in got["detail"]["skipped"]] == ["missing_column", "no_scheme"]


def test_model_inputs_are_matched_by_header(users, model, db):
    """年龄 is the positional column c8 of the training sample; in other samples it moves, and c8
    can be a different column altogether."""
    frame = model.frame
    noise = np.random.default_rng(1).integers(0, 100, len(frame))
    same = upload(users.ana, csv(frame), name="same").json()
    moved = upload(users.ana, csv(frame[["年龄", *frame.columns.drop("年龄")]]), name="moved").json()
    decoy = upload(users.ana, csv(frame.drop(columns=["年龄"]).assign(渠道评分=noise, 年龄=frame["年龄"])))
    decoy = decoy.json()
    assert {c["name"]: c["column_name"] for c in moved["columns"]}["年龄"] == "c1"
    columns = {c["name"]: c["column_name"] for c in decoy["columns"]}
    assert (columns["渠道评分"], columns["年龄"]) == ("c8", "c9")

    age = {"params": {"indicator_ids": [model.indicators["c8"]["id"]]}}  # the 年龄 indicator
    for kind, target in (
        ("score_psi", {"model_id": model.model["id"]}),
        ("indicator_psi", {"model_id": model.model["id"]}),
        ("indicator_psi", age),
    ):
        series = {}
        for ds in (same, moved, decoy):
            monitor = create(users.ana, kind, dataset_id=ds["id"], **target)
            got = run(users.ana, monitor)
            assert got["status"] == "done", got
            series[ds["id"]] = got["detail"]["series"]
        assert series[moved["id"]] == series[same["id"]], kind
        assert series[decoy["id"]] == series[same["id"]], kind


# ---- Decision checks ------------------------------------------------------------------------------


def test_approval_rate_compares_the_last_days_with_the_days_before(db):
    strategy = make_strategy(db)
    params = {"window_days": 7, "baseline_days": 30, "min_requests": 30}
    monitor = make_monitor(db, "approval_rate", strategy_id=strategy.id, params=params)
    current_start, baseline_start = NOW - timedelta(days=7), NOW - timedelta(days=37)
    code = strategy.code
    rows = [
        ("pass", NOW - timedelta(days=1), 34),
        ("pass", current_start, 1),  # a window includes its start
        ("reject", NOW - timedelta(days=2), 15),
        ("review", NOW - timedelta(hours=1), 5),
        ("pass", NOW - timedelta(days=20), 89),
        ("pass", baseline_start, 1),
        ("reject", NOW - timedelta(days=10), 9),
        ("reject", current_start - timedelta(seconds=1), 1),
    ]
    for decision, at, n in rows:
        log(db, code, decision, at, n=n)
    # Outside both windows, or another strategy's.
    log(db, code, "pass", baseline_start - timedelta(seconds=1), n=3)
    log(db, code, "reject", NOW, n=2)
    log(db, "OTHER", "pass", NOW - timedelta(days=1), n=4)
    db.commit()

    out = checks.approval_rate(db, monitor, now=NOW)
    detail = out.detail
    assert detail["current"] == {
        "pass": 35,
        "review": 5,
        "reject": 15,
        "total": 55,
        "rate": round(35 / 55, 6),
    }
    assert detail["baseline"] == {"pass": 90, "review": 0, "reject": 10, "total": 100, "rate": 0.9}
    assert out.value == pytest.approx(35 / 55 - 0.9, abs=1e-6)
    assert (detail["window_days"], detail["baseline_days"]) == (7, 30)
    assert detail["strategy"] == {"code": "RETAIL_APPLY"} and detail["period"] == "2026-11-13/2026-11-20"

    # A daily series by local date over both windows; days before the window are the reference.
    days: dict[str, dict[str, int]] = {}
    for decision, at, n in rows:
        day = days.setdefault(at.astimezone(TZ).date().isoformat(), {"pass": 0, "review": 0, "reject": 0})
        day[decision] += n
    assert [s["period"] for s in detail["series"]] == sorted(days)
    for s in detail["series"]:
        c = days[s["period"]]
        total = sum(c.values())
        assert (s["pass"], s["review"], s["reject"], s["rows"]) == (
            c["pass"],
            c["review"],
            c["reject"],
            total,
        )
        assert s["value"] == pytest.approx(c["pass"] / total, abs=1e-6)
        assert s["in_reference"] == (s["period"] < "2026-11-13")

    # Other windows.
    monitor.params = {"window_days": 1, "baseline_days": 7, "min_requests": 5}
    narrow = checks.approval_rate(db, monitor, now=NOW)
    # The day before NOW, then the 7 days before that (with both rows around the old window start).
    assert narrow.detail["current"]["total"] == 34 + 5 and narrow.detail["baseline"]["total"] == 15 + 1 + 1

    # Too few decisions on either side.
    monitor.params = params | {"min_requests": 56}
    with pytest.raises(CheckError) as caught:
        checks.approval_rate(db, monitor, now=NOW)
    assert caught.value.code == "too_few_requests"
    assert caught.value.detail == {"current": 55, "baseline": 100, "minimum": 56}
    monitor.params = params
    with pytest.raises(CheckError, match="Too few decisions"):
        checks.approval_rate(db, monitor, now=NOW + timedelta(days=60))


def test_rule_hit_rate_finds_the_rule_that_moved_most(db):
    strategy = make_strategy(db)
    monitor = make_monitor(db, "rule_hit_rate", strategy_id=strategy.id)
    code = strategy.code
    current, baseline = NOW - timedelta(days=1), NOW - timedelta(days=10)
    log(db, code, "reject", current, hits=["R01"], n=10)
    log(db, code, "reject", current, hits=["R02", "R09"], n=5)  # R09 is disabled
    log(db, code, "pass", current, n=35)
    log(db, code, "reject", baseline, hits=["R01"], n=10)
    log(db, code, "reject", baseline, hits=["R02", "OLD"], n=5)  # OLD is not in the rules any more
    log(db, code, "review", baseline, hits=["V01"], n=20)
    log(db, code, "pass", baseline, n=65)
    log(db, "OTHER", "reject", current, hits=["V01"], n=50)
    db.commit()

    out = checks.rule_hit_rate(db, monitor, now=NOW)
    detail = out.detail
    assert detail["strategy"] == {"code": "RETAIL_APPLY", "version": 1}
    assert (detail["current_total"], detail["baseline_total"]) == (50, 100)
    assert [(r["code"], r["decision"], r["current"], r["baseline"], r["shift"]) for r in detail["rules"]] == [
        ("R01", "reject", 0.2, 0.1, 0.1),
        ("R02", "reject", 0.1, 0.05, 0.05),
        ("V01", "review", 0.0, 0.2, -0.2),
    ]
    assert detail["worst"] == {
        "code": "V01",
        "name": "rule V01",
        "name_en": None,
        "decision": "review",
        "value": -0.2,
    }
    assert out.value == -0.2 and checks.level_of("rule_hit_rate", out.value, monitor.thresholds) == "alert"

    monitor.params = {"min_requests": 51}
    with pytest.raises(CheckError) as caught:
        checks.rule_hit_rate(db, monitor, now=NOW)
    assert caught.value.code == "too_few_requests" and caught.value.detail["current"] == 50

    # The rules of the online version, and only enabled ones.
    version = db.scalar(select(StrategyVersion).where(StrategyVersion.strategy_id == strategy.id))
    version.definition = {"default_decision": "pass", "rules": [RULES[3]]}
    db.commit()
    monitor.params = {}
    with pytest.raises(CheckError) as caught:
        checks.rule_hit_rate(db, monitor, now=NOW)
    assert caught.value.code == "empty_strategy"
    version.status = "retired"
    db.commit()
    with pytest.raises(CheckError) as caught:
        checks.rule_hit_rate(db, monitor, now=NOW)
    assert (caught.value.code, caught.value.detail) == ("strategy_not_online", {"strategy": "RETAIL_APPLY"})


# ---- Alerts follow the runs -----------------------------------------------------------------------


def test_runs_open_update_and_resolve_one_alert(db):
    strategy = shifted_strategy(db)
    monitor = make_monitor(
        db, "approval_rate", strategy_id=strategy.id, thresholds={"warn": 0.1, "alert": 0.5}
    )

    def step(warn: float, alert: float, **params) -> MonitorRun:
        monitor.thresholds = {"warn": warn, "alert": alert}
        monitor.params = params
        db.commit()
        return run_monitor(db, monitor, "manual")

    def unresolved() -> list[Alert]:
        query = select(Alert).where(Alert.monitor_id == monitor.id, Alert.status != "resolved")
        return list(db.scalars(query).unique())

    # A warning opens an alert.
    first = step(0.1, 0.5)
    assert (first.status, first.level, first.value, first.trigger) == ("done", "warn", -0.2, "manual")
    assert (monitor.last_level, monitor.last_value) == ("warn", -0.2) and monitor.last_run_at is not None
    [alert] = unresolved()
    assert (alert.status, alert.level, alert.peak_level, alert.value, alert.threshold) == (
        "open",
        "warn",
        "warn",
        -0.2,
        0.1,
    )
    assert (alert.occurrences, alert.run_id, alert.resolution) == (1, first.id, None)
    assert [(e["action"], e["level"], e["value"]) for e in alert.events] == [("opened", "warn", -0.2)]
    assert "actor" not in alert.events[0]
    assert set(alert.detail) == {"period", "strategy", "current", "baseline"}
    assert alert.detail["current"]["rate"] == 0.7 and alert.first_seen_at == alert.last_seen_at

    # Worse: escalated, and the peak follows.
    second = step(0.1, 0.15)
    [same] = unresolved()
    assert same.id == alert.id and second.level == "alert"
    assert (same.level, same.peak_level, same.threshold, same.occurrences, same.run_id) == (
        "alert",
        "alert",
        0.15,
        2,
        second.id,
    )
    assert [e["action"] for e in same.events] == ["opened", "escalated"] and same.events[-1][
        "level"
    ] == "alert"
    assert same.last_seen_at > same.first_seen_at

    # Better but still bad: eased, the peak stays.
    step(0.15, 0.3)
    [same] = unresolved()
    assert (same.level, same.peak_level, same.threshold, same.occurrences) == ("warn", "alert", 0.15, 3)
    assert [e["action"] for e in same.events] == ["opened", "escalated", "eased"]

    # The same level again only counts; a claimed alert stays claimed.
    same.status = "acknowledged"
    db.commit()
    fourth = step(0.15, 0.3)
    [same] = unresolved()
    assert (same.status, same.occurrences, same.run_id, len(same.events)) == ("acknowledged", 4, fourth.id, 3)

    # A failed run is recorded but leaves the alert alone.
    failed = step(0.15, 0.3, min_requests=1000)
    assert (failed.status, failed.level, failed.value, failed.code) == (
        "failed",
        "error",
        None,
        "too_few_requests",
    )
    assert failed.error == "Too few decisions to compare"
    assert failed.detail == {"code": "too_few_requests", "current": 50, "baseline": 100, "minimum": 1000}
    assert (monitor.last_level, monitor.last_value) == ("error", -0.2)
    [same] = unresolved()
    assert (same.status, same.level, same.occurrences, same.run_id) == ("acknowledged", "warn", 4, fourth.id)
    assert fourth.code is None

    # Normal again: resolved as recovered.
    recovered = step(0.5, 0.6)
    assert recovered.level == "normal" and unresolved() == []
    db.refresh(same)
    assert (same.status, same.resolution, same.run_id, same.resolved_by) == (
        "resolved",
        "recovered",
        recovered.id,
        None,
    )
    assert same.resolved_at is not None and same.events[-1] == same.events[-1] | {
        "action": "recovered",
        "value": -0.2,
    }
    step(0.5, 0.6)  # normal with nothing open changes nothing
    assert db.scalar(select(func.count()).select_from(Alert)) == 1

    # A later bad run opens a new alert.
    again = step(0.1, 0.5)
    [fresh] = unresolved()
    assert fresh.id != same.id and (fresh.status, fresh.occurrences, fresh.run_id) == ("open", 1, again.id)
    assert [e["action"] for e in fresh.events] == ["opened"]
    db.refresh(same)
    assert same.status == "resolved"
    statuses = db.scalars(select(MonitorRun.status).where(MonitorRun.monitor_id == monitor.id)).all()
    assert len(statuses) == 8 and statuses.count("failed") == 1

    # The database keeps one unresolved alert per monitor.
    db.add(Alert(monitor_id=monitor.id, status="acknowledged", level="warn", peak_level="warn"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Alert(monitor_id=monitor.id, status="resolved", level="warn", peak_level="warn"))
    db.commit()


def test_a_broken_check_fails_its_run(db, monkeypatch):
    strategy = shifted_strategy(db)
    monitor = make_monitor(db, "approval_rate", strategy_id=strategy.id)
    assert run_monitor(db, monitor, "manual").level == "alert"

    def broken(db, monitor):
        raise ZeroDivisionError("boom")

    monkeypatch.setitem(checks.CHECKS, "approval_rate", broken)  # the service shares this table
    got = run_monitor(db, monitor, "schedule")
    assert (got.status, got.level, got.error, got.code) == (
        "failed",
        "error",
        "ZeroDivisionError: boom",
        "internal_error",
    )
    assert db.scalar(select(Alert.status).where(Alert.monitor_id == monitor.id)) == "open"


# ---- Monitors API ---------------------------------------------------------------------------------


def test_create_checks_the_target_of_each_kind(users, db):
    ana = users.ana
    model = RiskModel(code="RETAIL_APP", name="评分卡")
    db.add(model)
    db.commit()
    strategy = make_strategy(db)
    dataset = upload(ana, csv(loan_frame(rows=60)), name="loans").json()
    m, s, d = str(model.id), str(strategy.id), dataset["id"]

    def code(kind_, **fields):
        response = ana.post(f"{API}/monitors", json={"name": "m", "kind": kind_} | fields)
        assert response.status_code in (404, 422), response.json()
        return response.json()["code"]

    assert code("score_psi", dataset_id=d) == "model_required"
    assert code("model_ks", dataset_id=d) == "model_required"
    assert code("score_psi", model_id=m, strategy_id=s, dataset_id=d) == "invalid_target"
    # Without an online version there is no training sample to default to.
    assert code("score_psi", model_id=m) == "dataset_required"
    assert code("indicator_psi", dataset_id=d) == "indicators_required"
    assert code("approval_rate") == "strategy_required"
    assert code("rule_hit_rate", strategy_id=s, model_id=m) == "invalid_target"
    assert code("approval_rate", strategy_id=s, dataset_id=d) == "invalid_target"
    assert code("approval_rate", strategy_id=s, params={"indicator_ids": [MISSING]}) == "invalid_target"
    assert (
        code("model_ks", model_id=m, dataset_id=d, params={"indicator_ids": [MISSING]})
        == "indicator_not_found"
    )
    [income] = ana.post(f"{API}/indicators/import", json={"dataset_id": d, "columns": ["income"]}).json()
    ids = {"indicator_ids": [income["id"]]}
    assert code("model_ks", model_id=m, dataset_id=d, params=ids) == "invalid_target"
    assert code("score_psi", model_id=MISSING, dataset_id=d) == "model_not_found"
    assert code("approval_rate", strategy_id=MISSING) == "strategy_not_found"
    assert code("score_psi", model_id=m, dataset_id=MISSING) == "dataset_not_found"
    for bad in (
        {"thresholds": {"warn": 0.3, "alert": 0.2}},
        {"thresholds": {"warn": -1, "alert": 0.2}},
        {"thresholds": {"warn": 0.1}},
        {"schedule": {"freq": "daily", "hour": 24}},
        {"schedule": {"freq": "monthly"}},
        {"params": {"window_days": 0}},
        {"params": {"reference": {"start": "2026-1", "end": "2026-02"}}},
        {"name": ""},
        {"kind": "bogus"},
    ):
        assert code("approval_rate", **({"strategy_id": s} | bad)) == "validation_error", bad

    # Valid ones; the indicator check needs no model when given indicators.
    assert create(ana, "indicator_psi", dataset_id=d, params=ids)["params"]["indicator_ids"] == [income["id"]]
    equal = create(ana, "approval_rate", strategy_id=s, thresholds={"warn": 0.2, "alert": 0.2})
    assert equal["thresholds"] == {"warn": 0.2, "alert": 0.2}
    assert db.scalar(select(func.count()).select_from(Monitor)) == 2


def test_monitor_crud_and_schedules(users, db):
    strategy = make_strategy(db)
    before = datetime.now(UTC)
    created = create(users.ana, "approval_rate", name=" 通过率 ", strategy_id=str(strategy.id))
    assert created["name"] == "通过率" and created["owner"]["username"] == "ana"
    assert created["strategy"] == {
        "id": str(strategy.id),
        "code": "RETAIL_APPLY",
        "name": "策略 RETAIL_APPLY",
        "name_en": "Strategy RETAIL_APPLY",
    }
    assert (created["model"], created["dataset"]) == (None, None)
    assert created["thresholds"] == DEFAULT_THRESHOLDS["approval_rate"] == {"warn": 0.05, "alert": 0.1}
    assert created["params"] == {
        "indicator_ids": [],
        "window_days": 7,
        "baseline_days": 30,
        "min_requests": 30,
    }
    assert created["schedule"] == {"freq": "daily", "hour": 6, "minute": 0, "weekday": 0}
    assert created["enabled"] is True
    assert (created["last_run_at"], created["last_level"], created["last_value"]) == (None, None, None)
    assert (created["trend"], created["alert"], created["latest"], created["runs"]) == ([], None, None, [])
    due = datetime.fromisoformat(created["next_run_at"])
    assert before < due <= before + timedelta(days=1)
    assert (due.astimezone(TZ).hour, due.astimezone(TZ).minute) == (6, 0)

    disabled = create(users.bob, "rule_hit_rate", strategy_id=str(strategy.id), enabled=False)
    manual = create(users.ana, "rule_hit_rate", strategy_id=str(strategy.id), schedule={"freq": "manual"})
    assert disabled["next_run_at"] is None and manual["next_run_at"] is None

    listed = users.bob.get(f"{API}/monitors").json()
    assert [m["id"] for m in listed] == [created["id"], disabled["id"], manual["id"]]
    assert len(users.bob.get(f"{API}/monitors", params={"strategy_id": str(strategy.id)}).json()) == 3
    assert users.bob.get(f"{API}/monitors", params={"model_id": MISSING}).json() == []
    assert users.bob.get(f"{API}/monitors/{created['id']}").json() == created
    assert users.bob.get(f"{API}/monitors/{MISSING}").json()["code"] == "monitor_not_found"

    # Owner or admin only; every change recomputes the next run.
    url = f"{API}/monitors/{created['id']}"
    assert users.bob.patch(url, json={"name": "x"}).json()["code"] == "forbidden"
    assert users.bob.delete(url).json()["code"] == "forbidden"
    hourly = users.ana.patch(url, json={"schedule": {"freq": "hourly", "minute": 15}}).json()
    due = datetime.fromisoformat(hourly["next_run_at"])
    assert datetime.now(UTC) < due <= datetime.now(UTC) + timedelta(hours=1) and due.minute == 15
    assert hourly["schedule"] == {"freq": "hourly", "hour": 6, "minute": 15, "weekday": 0}
    off = users.ana.patch(url, json={"enabled": False}).json()
    assert (off["enabled"], off["next_run_at"]) == (False, None)
    on = users.root.patch(url, json={"enabled": True, "thresholds": {"warn": 0.02, "alert": 0.04}}).json()
    assert on["next_run_at"] is not None and on["thresholds"] == {"warn": 0.02, "alert": 0.04}
    assert users.ana.patch(url, json={"name": " 新名称 "}).json()["name"] == "新名称"
    weekly = {"freq": "weekly", "weekday": 2, "hour": 8, "minute": 30}
    due = datetime.fromisoformat(users.ana.patch(url, json={"schedule": weekly}).json()["next_run_at"])
    assert (due.astimezone(TZ).weekday(), due.astimezone(TZ).hour, due.astimezone(TZ).minute) == (2, 8, 30)
    assert users.ana.patch(url, json={"schedule": {"freq": "manual"}}).json()["next_run_at"] is None
    assert users.ana.patch(url, json={"thresholds": {"warn": 0.5, "alert": 0.1}}).status_code == 422
    assert users.ana.patch(url, json={"dataset_id": MISSING}).json()["code"] == "invalid_target"
    params = users.ana.patch(url, json={"params": {"window_days": 3}}).json()["params"]
    assert (params["window_days"], params["baseline_days"]) == (3, 30)
    assert users.ana.patch(f"{API}/monitors/{MISSING}", json={}).json()["code"] == "monitor_not_found"

    # Deleting removes the runs and alerts too.
    monitor = db.get(Monitor, uuid.UUID(manual["id"]))
    shifted_strategy(db, "SHIFTED")  # decisions for another strategy: this one fails
    run_monitor(db, monitor, "manual")
    make_alert(db, monitor)
    assert users.root.delete(f"{API}/monitors/{manual['id']}").status_code == 204
    assert users.ana.delete(url).status_code == 204
    assert users.ana.get(url).status_code == 404
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(MonitorRun)) == 0
    assert db.scalar(select(func.count()).select_from(Alert)) == 0
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "monitor")).all()
    assert sorted(set(actions)) == ["monitor.created", "monitor.deleted", "monitor.updated"]
    assert actions.count("monitor.created") == 3 and actions.count("monitor.deleted") == 2
    updated = db.scalars(select(AuditLog).where(AuditLog.action == "monitor.updated")).all()
    assert updated[0].detail == {"name": "通过率", "fields": ["schedule"]}


def test_model_monitors_default_to_the_training_sample(users, model, db):
    monitor = create(
        users.ana, "model_ks", model_id=model.model["id"], schedule={"freq": "hourly", "minute": 0}
    )
    assert monitor["dataset"] == {"id": model.dataset["id"], "name": "train"}
    assert monitor["model"]["code"] == "RETAIL_APP" and monitor["strategy"] is None
    assert (
        users.ana.get(f"{API}/monitors", params={"model_id": model.model["id"]}).json()[0]["id"]
        == monitor["id"]
    )
    # An explicit dataset wins.
    copy = upload(users.ana, csv(model.frame), name="copy").json()
    other = create(users.ana, "score_psi", model_id=model.model["id"], dataset_id=copy["id"])
    assert other["dataset"]["id"] == copy["id"]


def test_run_now_returns_the_detail(users, db):
    strategy = shifted_strategy(db)
    monitor = create(users.ana, "approval_rate", strategy_id=str(strategy.id))
    response = users.bob.post(f"{API}/monitors/{monitor['id']}/run")  # anyone may run a monitor
    assert response.status_code == 200, response.json()
    detail = response.json()
    [newest] = detail["runs"]
    assert detail["latest"]["id"] == newest["id"] and detail["latest"]["detail"]["current"]["rate"] == 0.7
    assert (newest["trigger"], newest["status"], newest["level"], newest["value"], newest["code"]) == (
        "manual",
        "done",
        "alert",
        -0.2,
        None,
    )
    assert "detail" not in newest and newest["seconds"] >= 0
    assert (detail["last_level"], detail["last_value"]) == ("alert", -0.2) and detail["last_run_at"]
    assert detail["alert"] == {"id": detail["alert"]["id"], "status": "open", "level": "alert"}
    assert detail["trend"] == [s["value"] for s in detail["latest"]["detail"]["series"]][-12:]
    bob = db.scalar(select(User).where(User.username == "bob"))
    assert db.get(MonitorRun, newest["id"]).created_by == bob.id
    got = users.ana.get(f"{API}/monitor-runs/{newest['id']}").json()
    assert got == detail["latest"]
    assert users.ana.get(f"{API}/monitor-runs/999999").json()["code"] == "run_not_found"
    assert users.ana.post(f"{API}/monitors/{MISSING}/run").json()["code"] == "monitor_not_found"

    # A failed run is listed first but the latest result stays the last good one.
    users.ana.patch(f"{API}/monitors/{monitor['id']}", json={"params": {"min_requests": 1000}})
    detail = users.ana.post(f"{API}/monitors/{monitor['id']}/run").json()
    failed, done = detail["runs"]
    assert (failed["status"], failed["level"], failed["code"], failed["value"]) == (
        "failed",
        "error",
        "too_few_requests",
        None,
    )
    assert failed["error"] == "Too few decisions to compare" and done["code"] is None
    assert detail["latest"]["id"] == done["id"] and detail["last_level"] == "error"
    assert users.ana.get(f"{API}/monitor-runs/{failed['id']}").json()["code"] == "too_few_requests"
    actions = db.scalars(select(AuditLog).where(AuditLog.action == "monitor.run")).all()
    assert [a.detail["level"] for a in actions] == ["alert", "error"]

    # Checks without a series trend on their recent values, oldest first.
    rules = create(users.ana, "rule_hit_rate", strategy_id=str(strategy.id))
    users.ana.post(f"{API}/monitors/{rules['id']}/run")
    users.ana.patch(f"{API}/monitors/{rules['id']}", json={"params": {"window_days": 2}})
    users.ana.post(f"{API}/monitors/{rules['id']}/run")
    listed = {m["id"]: m for m in users.ana.get(f"{API}/monitors").json()}
    values = [r["value"] for r in reversed(users.ana.get(f"{API}/monitors/{rules['id']}").json()["runs"])]
    assert listed[rules["id"]]["trend"] == values and len(values) == 2
    assert (
        listed[monitor["id"]]["trend"] == detail["trend"]
        and listed[monitor["id"]]["alert"]["level"] == "alert"
    )


# ---- Alert centre ---------------------------------------------------------------------------------


def test_alerts_are_listed_unresolved_and_severe_first(users, db):
    strategy = make_strategy(db)
    m1, m2, m3, m4 = (
        make_monitor(db, "approval_rate", name=f"m{i}", strategy_id=strategy.id) for i in range(1, 5)
    )
    now = datetime.now(UTC)
    old = make_alert(db, m1, "resolved", "alert", seen=now - timedelta(hours=1), resolution="recovered")
    a1 = make_alert(db, m1, "open", "alert", seen=now - timedelta(hours=3))
    a2 = make_alert(db, m2, "open", "warn", seen=now - timedelta(hours=1))
    a3 = make_alert(db, m3, "acknowledged", "warn", seen=now - timedelta(hours=2))
    a4 = make_alert(db, m4, "acknowledged", "alert", seen=now - timedelta(hours=5))
    done = make_alert(db, m2, "resolved", "warn", seen=now, resolution="manual")

    def ids(**params) -> list[int]:
        response = users.bob.get(f"{API}/alerts", params=params)
        assert response.status_code == 200, response.json()
        page = response.json()
        assert page["counts"] == {"open": 2, "acknowledged": 2, "resolved": 2, "warn": 2, "alert": 2}
        return [a["id"] for a in page["items"]]

    assert ids() == [a1.id, a4.id, a2.id, a3.id, old.id, done.id]
    assert ids(status="active") == [a1.id, a4.id, a2.id, a3.id]
    assert ids(status="open") == [a1.id, a2.id]
    assert ids(status="acknowledged") == [a4.id, a3.id]
    assert ids(status="resolved") == [old.id, done.id]
    assert ids(level="warn") == [a2.id, a3.id, done.id]
    assert ids(level="alert", status="active") == [a1.id, a4.id]
    assert ids(monitor_id=str(m1.id)) == [a1.id, old.id]
    assert ids(monitor_id=MISSING) == []
    assert ids(size=2, page=2) == [a2.id, a3.id]
    page = users.bob.get(f"{API}/alerts", params={"size": 2, "status": "active"}).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    for bad in ({"status": "closed"}, {"level": "normal"}, {"size": 0}, {"page": 0}, {"size": 101}):
        assert users.bob.get(f"{API}/alerts", params=bad).status_code == 422, bad

    item = users.bob.get(f"{API}/alerts/{a1.id}").json()
    assert item["monitor"] == {
        "id": str(m1.id),
        "name": "m1",
        "kind": "approval_rate",
        "model": None,
        "strategy": {
            "id": str(strategy.id),
            "code": "RETAIL_APPLY",
            "name": "策略 RETAIL_APPLY",
            "name_en": "Strategy RETAIL_APPLY",
        },
        "thresholds": {"warn": 0.05, "alert": 0.1},
    }
    assert (item["status"], item["level"], item["threshold"], item["assignee"], item["resolver"]) == (
        "open",
        "alert",
        0.1,
        None,
        None,
    )
    assert users.bob.get(f"{API}/alerts/999999").json()["code"] == "alert_not_found"
    # The monitor list shows each monitor's unresolved alert.
    listed = {m["name"]: m["alert"] for m in users.bob.get(f"{API}/monitors").json()}
    assert listed == {
        "m1": {"id": a1.id, "status": "open", "level": "alert"},
        "m2": {"id": a2.id, "status": "open", "level": "warn"},
        "m3": {"id": a3.id, "status": "acknowledged", "level": "warn"},
        "m4": {"id": a4.id, "status": "acknowledged", "level": "alert"},
    }


def test_acknowledge_and_resolve(users, db):
    strategy = shifted_strategy(db)
    monitor = create(users.ana, "approval_rate", strategy_id=str(strategy.id))
    alert_id = users.ana.post(f"{API}/monitors/{monitor['id']}/run").json()["alert"]["id"]
    url = f"{API}/alerts/{alert_id}"

    claimed = users.bob.post(f"{url}/acknowledge", json={"note": " 正在核实 "})
    assert claimed.status_code == 200, claimed.json()
    claimed = claimed.json()
    assert (claimed["status"], claimed["assignee"]["username"], claimed["note"]) == (
        "acknowledged",
        "bob",
        "正在核实",
    )
    assert claimed["acknowledged_at"] and claimed["resolved_at"] is None
    event = claimed["events"][-1]
    assert (event["action"], event["note"], event["actor"]["display_name"]) == (
        "acknowledged",
        "正在核实",
        "bob",
    )
    again = users.ana.post(f"{url}/acknowledge", json={})
    assert again.status_code == 409 and again.json()["code"] == "invalid_transition"
    assert again.json()["detail"] == {"status": "acknowledged"}

    for note in ({}, {"note": ""}, {"note": "   "}):
        response = users.ana.post(f"{url}/resolve", json=note)
        assert response.status_code == 422 and response.json()["code"] == "note_required", note
    assert users.ana.post(f"{url}/resolve", json={"note": "x" * 1001}).status_code == 422
    resolved = users.ana.post(f"{url}/resolve", json={"note": " 渠道数据已修复 "}).json()
    assert (resolved["status"], resolved["resolution"], resolved["resolver"]["username"]) == (
        "resolved",
        "manual",
        "ana",
    )
    assert resolved["note"] == "渠道数据已修复" and resolved["resolved_at"]
    assert resolved["assignee"]["username"] == "bob"  # who claimed it stays on record
    assert [e["action"] for e in resolved["events"]] == ["opened", "acknowledged", "resolved"]
    for action in ("resolve", "acknowledge"):
        response = users.ana.post(f"{url}/{action}", json={"note": "again"})
        assert response.status_code == 409 and response.json()["detail"] == {"status": "resolved"}, action

    # The next bad run opens a new alert, which can be resolved without being claimed first.
    fresh = users.ana.post(f"{API}/monitors/{monitor['id']}/run").json()["alert"]
    assert fresh["id"] != alert_id and fresh["status"] == "open"
    closed = users.root.post(f"{API}/alerts/{fresh['id']}/resolve", json={"note": "accepted"}).json()
    assert closed["status"] == "resolved" and closed["assignee"] is None and closed["acknowledged_at"] is None
    assert users.ana.post(f"{API}/alerts/999999/acknowledge", json={}).json()["code"] == "alert_not_found"
    assert (
        users.ana.post(f"{API}/alerts/999999/resolve", json={"note": "x"}).json()["code"] == "alert_not_found"
    )
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "alert")).all()
    assert sorted(actions) == ["alert.acknowledged", "alert.resolved", "alert.resolved"]
    logged = db.scalar(select(AuditLog).where(AuditLog.action == "alert.acknowledged"))
    assert (logged.entity_id, logged.detail) == (str(alert_id), {"name": "approval_rate"})


def test_monitoring_requires_sign_in(anon):
    monitor, alert = f"{API}/monitors/{MISSING}", f"{API}/alerts/1"
    for response in (
        anon.get(f"{API}/monitors"),
        anon.post(f"{API}/monitors", json={"name": "x", "kind": "approval_rate"}),
        anon.get(monitor),
        anon.patch(monitor, json={}),
        anon.delete(monitor),
        anon.post(f"{monitor}/run"),
        anon.get(f"{API}/monitor-runs/1"),
        anon.get(f"{API}/alerts"),
        anon.get(alert),
        anon.post(f"{alert}/acknowledge", json={}),
        anon.post(f"{alert}/resolve", json={"note": "x"}),
        anon.get(f"{API}/overview"),
        anon.get(f"{API}/stability"),
    ):
        assert response.status_code == 401, response.request.url


# ---- Scheduling -----------------------------------------------------------------------------------


def test_due_monitors_are_claimed_and_moved_forward(db):
    strategy = shifted_strategy(db)
    now = datetime.now(UTC)
    hourly = {"freq": "hourly", "hour": 6, "minute": 5, "weekday": 0}

    def monitor(name, next_run_at, enabled=True, schedule=hourly):
        return make_monitor(
            db,
            "approval_rate",
            name=name,
            strategy_id=strategy.id,
            schedule=schedule,
            enabled=enabled,
            next_run_at=next_run_at,
        )

    late = monitor("late", now - timedelta(hours=3))
    due = monitor("due", now - timedelta(minutes=1))
    future = monitor("future", now + timedelta(hours=1))
    disabled = monitor("disabled", now - timedelta(minutes=1), enabled=False)
    manual = monitor("manual", None, schedule={"freq": "manual"})

    claimed = due_monitors(db, now)
    assert [m.name for m in claimed] == ["late", "due"]  # the longest waiting first
    for m in (late, due):
        db.refresh(m)
        # Missed runs are not caught up: the next one is the first after now.
        assert m.next_run_at == next_run(hourly, now) and m.next_run_at > now
    for m, expected in ((future, now + timedelta(hours=1)), (disabled, now - timedelta(minutes=1))):
        db.refresh(m)
        assert m.next_run_at == expected
    db.refresh(manual)
    assert manual.next_run_at is None
    assert due_monitors(db, now) == []
    assert db.scalar(select(func.count()).select_from(MonitorRun)) == 0  # claiming runs nothing


def test_the_worker_tick_runs_due_monitors(db, monkeypatch):
    strategy = shifted_strategy(db)
    now = datetime.now(UTC)
    due = make_monitor(db, "approval_rate", strategy_id=strategy.id, next_run_at=now - timedelta(seconds=5))
    waiting = make_monitor(db, "rule_hit_rate", strategy_id=strategy.id, next_run_at=now + timedelta(hours=1))
    off = make_monitor(db, "rule_hit_rate", strategy_id=strategy.id, next_run_at=now, enabled=False)

    assert schedule_due() == 1
    [run_] = db.scalars(select(MonitorRun)).all()
    assert (run_.monitor_id, run_.trigger, run_.status, run_.level, run_.created_by) == (
        due.id,
        "schedule",
        "done",
        "alert",
        None,
    )
    db.refresh(due)
    assert due.next_run_at > now and due.last_level == "alert" and due.last_run_at is not None
    for m in (waiting, off):
        db.refresh(m)
        assert m.last_run_at is None
    assert db.scalar(select(Alert.level).where(Alert.monitor_id == due.id)) == "alert"
    assert schedule_due() == 0

    # The worker runs registered ticks; a failing tick does not stop the others.
    assert schedule_due in jobs.TICKS
    calls = []
    monkeypatch.setattr(jobs, "TICKS", [lambda: 1 / 0, lambda: calls.append("ran"), *jobs.TICKS])
    due.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    jobs.run_ticks()
    assert calls == ["ran"]
    assert (
        db.scalar(select(func.count()).select_from(MonitorRun).where(MonitorRun.trigger == "schedule")) == 2
    )


# ---- Overview and stability -----------------------------------------------------------------------


def online_model(db, code, approved_at, focus="oot") -> tuple[RiskModel, ModelVersion]:
    model = RiskModel(code=code, name=f"模型 {code}")
    db.add(model)
    db.flush()
    db.add(ModelVersion(model_id=model.id, version=1, status="retired", approved_at=approved_at))
    version = ModelVersion(
        model_id=model.id,
        version=2,
        status="online",
        result={"focus": focus},
        approved_at=approved_at,
        auc_train=0.8,
        ks_train=0.5,
        auc_test=0.78,
        ks_test=0.45,
        auc_oot=0.75,
        ks_oot=0.4,
    )
    db.add(version)
    db.commit()
    return model, version


def add_run(db, monitor, *, value=None, level="normal", status="done", detail=None, at=None) -> MonitorRun:
    run_ = MonitorRun(
        monitor_id=monitor.id,
        trigger="manual",
        status=status,
        level=level if status == "done" else "error",
        value=value,
        detail=detail or {},
        created_at=at or datetime.now(UTC),
    )
    db.add(run_)
    db.commit()
    return run_


def test_overview(users, db):
    now = datetime.now(UTC)
    today = now.astimezone(TZ).date()
    first = today - timedelta(days=29)
    start = datetime.combine(first, time(), TZ).astimezone(UTC)
    prev_start = start - timedelta(days=30)

    retail, retail_v = online_model(db, "RETAIL_APP", now - timedelta(days=10))
    newer, newer_v = online_model(db, "NEWER", now - timedelta(days=1), focus="test")
    apply = make_strategy(db, rules=[rule("R01", "model:RETAIL_APP.score", "lt", 500), *RULES[1:]])
    other = make_strategy(db, "OTHER", rules=[rule("X01", "age", "lt", 18)])
    version = db.scalar(select(StrategyVersion).where(StrategyVersion.strategy_id == apply.id))
    effect = {"pass": 0.03, "review": 0.08, "reject": 0.21}
    version.backtest = {
        "dataset": {"id": MISSING, "name": "loans"},
        "summary": {"bad_rate_by_decision": effect},
    }
    db.commit()

    ap, ot = "RETAIL_APPLY", "OTHER"
    current = [
        (ap, "pass", start, [], "api"),  # the window starts at local midnight 29 days ago
        (ap, "reject", now - timedelta(minutes=2), ["R01"], "api"),
        (ap, "reject", start + timedelta(days=1, hours=3), ["R01", "R02"], "api"),
        (ap, "review", now - timedelta(days=3), ["V01"], "api"),
        (ap, "reject", now - timedelta(days=4), ["R02"], "api"),
        (ap, "pass", now - timedelta(days=5), [], "console"),
        (ap, "pass", now - timedelta(days=6), [], "demo"),
        (ap, "pass", now - timedelta(days=6), [], "demo"),
        *[(ot, "pass", now - timedelta(days=1), [], "api")] * 3,
    ]
    previous = [
        (ap, "reject", start - timedelta(seconds=1), ["R01"], "api"),
        (ot, "pass", prev_start, [], "api"),
    ]
    outside = [
        (ap, "pass", prev_start - timedelta(seconds=1), [], "api"),
        (ap, "reject", now + timedelta(hours=1), ["R01"], "api"),
    ]
    for code, decision, at, hits, source in current + previous + outside:
        log(db, code, decision, at, hits=hits, source=source)

    # Monitors: the first score monitor has no run yet; the second has two good runs and a failed one.
    empty = make_monitor(db, "score_psi", name="score (new)", model_id=retail.id)
    score = make_monitor(db, "score_psi", name="score", model_id=retail.id)
    add_run(db, score, value=0.05, at=now - timedelta(days=2))
    good = add_run(
        db, score, value=0.12, level="warn", detail={"period": "2026-06"}, at=now - timedelta(days=1)
    )
    add_run(db, score, status="failed", at=now - timedelta(hours=1))
    make_monitor(db, "approval_rate", name="off", strategy_id=apply.id, enabled=False)
    watched = [make_monitor(db, "approval_rate", name=f"a{i}", strategy_id=other.id) for i in range(6)]
    alerts = [make_alert(db, m, level="alert" if i == 4 else "warn") for i, m in enumerate(watched)]
    make_alert(db, watched[0], "resolved", resolution="manual", seen=now - timedelta(days=3))

    got = users.ana.get(f"{API}/overview").json()
    assert (got["as_of"], got["timezone"]) == (today.isoformat(), "Asia/Shanghai")
    decisions = got["decisions"]
    assert decisions["current"] == {
        "pass": 7,
        "review": 1,
        "reject": 3,
        "total": 11,
        "approval_rate": round(7 / 11, 6),
    }
    assert decisions["previous"] == {"pass": 1, "review": 0, "reject": 1, "total": 2, "approval_rate": 0.5}
    assert decisions["sources"] == {"api": 8, "console": 1, "demo": 2}
    daily = decisions["daily"]
    assert [d["date"] for d in daily] == [(first + timedelta(days=i)).isoformat() for i in range(30)]
    expected: dict[str, dict[str, int]] = {}
    for _, decision, at, _, _ in current:
        day = expected.setdefault(at.astimezone(TZ).date().isoformat(), {"pass": 0, "review": 0, "reject": 0})
        day[decision] += 1
    for d in daily:
        c = expected.get(d["date"], {"pass": 0, "review": 0, "reject": 0})
        total = sum(c.values())
        assert d == {
            "date": d["date"],
            **c,
            "total": total,
            "approval_rate": round(c["pass"] / total, 6) if total else None,
        }
    assert daily[0]["pass"] >= 1 and sum(d["total"] for d in daily) == 11

    # The online strategy with the most decisions, and what its rules hit.
    strategy = got["strategy"]
    assert (strategy["id"], strategy["code"], strategy["version"], strategy["version_id"]) == (
        str(apply.id),
        ap,
        1,
        str(version.id),
    )
    assert strategy["name"] == {"zh": "策略 RETAIL_APPLY", "en": "Strategy RETAIL_APPLY"}
    assert strategy["decisions"] == {"pass": 4, "review": 1, "reject": 3, "total": 8, "approval_rate": 0.5}
    assert strategy["rules"] == [
        {
            "code": "R01",
            "label": {"zh": "rule R01", "en": "rule R01"},
            "decision": "reject",
            "hits": 2,
            "hit_rate": 0.25,
            "exclusive": 1,
        },
        {
            "code": "R02",
            "label": {"zh": "rule R02", "en": "rule R02"},
            "decision": "reject",
            "hits": 2,
            "hit_rate": 0.25,
            "exclusive": 1,
        },
        {
            "code": "V01",
            "label": {"zh": "rule V01", "en": "rule V01"},
            "decision": "review",
            "hits": 1,
            "hit_rate": 0.125,
            "exclusive": 1,
        },
    ]  # R09 is disabled
    assert (strategy["effect"], strategy["effect_dataset"]) == (effect, "loans")

    # The model the strategy scores with, though another went online later.
    assert got["model"] == {
        "id": str(retail.id),
        "code": "RETAIL_APP",
        "name": {"zh": "模型 RETAIL_APP", "en": "模型 RETAIL_APP"},
        "version": 2,
        "version_id": str(retail_v.id),
        "focus": "oot",
        "auc_train": 0.8,
        "ks_train": 0.5,
        "auc_focus": 0.75,
        "ks_focus": 0.4,
    }
    psi = got["score_psi"]
    assert datetime.fromisoformat(psi.pop("ran_at")) == good.created_at
    assert psi == {
        "monitor_id": str(score.id),
        "value": 0.12,
        "level": "warn",
        "period": "2026-06",
        "thresholds": {"warn": 0.1, "alert": 0.25},
    }

    # Active alerts (at most five, the severe first) and the enabled monitors.
    assert got["alerts"]["counts"] == {"open": 6, "acknowledged": 0, "resolved": 1, "warn": 5, "alert": 1}
    items = got["alerts"]["items"]
    assert len(items) == 5 and items[0]["id"] == alerts[4].id and all(a["status"] == "open" for a in items)
    assert [m["name"] for m in got["monitors"]] == ["score (new)", "score", *[f"a{i}" for i in range(6)]]
    assert got["monitors"][1]["trend"] == [0.05, 0.12] and got["monitors"][0]["id"] == str(empty.id)

    # More traffic on OTHER makes it the primary strategy; it scores with no model.
    log(db, ot, "reject", now - timedelta(hours=2), hits=["X01"], n=10)
    db.commit()
    got = users.ana.get(f"{API}/overview").json()
    strategy = got["strategy"]
    assert strategy["code"] == ot and strategy["decisions"]["total"] == 13
    assert strategy["rules"] == [
        {
            "code": "X01",
            "label": {"zh": "rule X01", "en": "rule X01"},
            "decision": "reject",
            "hits": 10,
            "hit_rate": round(10 / 13, 6),
            "exclusive": 10,
        }
    ]
    assert (strategy["effect"], strategy["effect_dataset"]) == (None, None)
    # The most recently approved online model then, which has no score monitor.
    model = got["model"]
    assert (model["code"], model["version_id"], model["focus"], model["auc_focus"], model["ks_focus"]) == (
        "NEWER",
        str(newer_v.id),
        "test",
        0.78,
        0.45,
    )
    assert got["score_psi"] is None


def test_overview_of_an_empty_platform(users):
    got = users.ana.get(f"{API}/overview").json()
    zero = {"pass": 0, "review": 0, "reject": 0, "total": 0, "approval_rate": None}
    assert got["decisions"]["current"] == got["decisions"]["previous"] == zero
    assert got["decisions"]["sources"] == {}
    daily = got["decisions"]["daily"]
    assert len(daily) == 30 and daily[-1]["date"] == got["as_of"]
    assert all(d | {"date": None} == zero | {"date": None} for d in daily)
    assert (got["strategy"], got["model"], got["score_psi"], got["monitors"]) == (None, None, None, [])
    assert got["alerts"] == {
        "counts": {"open": 0, "acknowledged": 0, "resolved": 0, "warn": 0, "alert": 0},
        "items": [],
    }
    assert users.ana.get(f"{API}/stability").json() == {"models": [], "model": None}


def test_stability_stitches_the_latest_runs_of_one_model(users, db):
    old = RiskModel(code="OLD_APP", name="旧模型", name_en="Old")
    db.add(old)
    db.commit()
    retail, _ = online_model(db, "RETAIL_APP", datetime.now(UTC))
    strategy = make_strategy(db)
    make_monitor(db, "approval_rate", strategy_id=strategy.id)  # not a model monitor
    old_score = make_monitor(db, "score_psi", model_id=old.id, thresholds={"warn": 0.2, "alert": 0.3})
    add_run(
        db,
        old_score,
        value=0.01,
        detail={
            "reference": ["2025-01", "2025-03"],
            "series": [{"period": "2025-04", "value": 0.01, "rows": 9, "in_reference": False}],
        },
    )
    off = make_monitor(db, "score_psi", name="disabled score", model_id=retail.id, enabled=False)
    add_run(db, off, value=9.9, detail={"series": [{"period": "2026-01", "value": 9.9}]})
    score = make_monitor(db, "score_psi", model_id=retail.id, thresholds={"warn": 0.15, "alert": 0.3})
    ks = make_monitor(db, "model_ks", model_id=retail.id)
    features = make_monitor(db, "indicator_psi", model_id=retail.id)

    def month(period, **fields):
        return {"period": period, "rows": 100, "in_reference": False} | fields

    add_run(db, score, value=0.5, detail={"series": [month("2026-01", value=0.5)]})  # superseded
    add_run(
        db,
        score,
        value=0.31,
        level="alert",
        detail={
            "reference": ["2026-03", "2026-04"],
            "series": [
                month("2026-03", value=0.01, bad_rate=0.05, in_reference=True),
                month("2026-04", value=0.02, bad_rate=0.06, in_reference=True),
                month("2026-05", value=0.12, bad_rate=0.07),
                month("2026-06", value=0.31, bad_rate=None, rows=80),
            ],
        },
    )
    add_run(
        db,
        ks,
        value=0.3,
        detail={
            "reference": ["2026-02", "2026-03"],
            "reference_metrics": {"auc": 0.8, "ks": 0.5, "labelled": 200},
            "series": [
                month("2026-02", auc=0.81, ks=0.52, rows=90, bad_rate=0.04, in_reference=True),
                month("2026-03", auc=0.8, ks=0.5, bad_rate=0.09),
                month("2026-05", auc=0.7, ks=0.35, bad_rate=0.08),
            ],
        },
    )
    add_run(
        db,
        features,
        value=0.4,
        detail={
            "series": [month("2026-04", value=0.0), month("2026-05", value=0.2), month("2026-06", value=0.4)],
            "indicators": [
                {
                    "code": "income",
                    "name": "月收入",
                    "name_en": "Income",
                    "values": [0.0, 0.2, 0.4],
                    "latest": 0.4,
                },
                {"code": "c8", "name": "年龄", "name_en": None, "values": [0.0, 0.01, 0.02], "latest": 0.02},
            ],
        },
    )
    alert = make_alert(db, score, level="alert")
    make_alert(db, old_score)

    got = users.ana.get(f"{API}/stability").json()
    assert got["models"] == [
        {"id": str(old.id), "code": "OLD_APP", "name": {"zh": "旧模型", "en": "Old"}},
        {
            "id": str(retail.id),
            "code": "RETAIL_APP",
            "name": {"zh": "模型 RETAIL_APP", "en": "模型 RETAIL_APP"},
        },
    ]
    assert got["model"]["id"] == str(retail.id)  # the online one, though OLD_APP was monitored first
    assert got["months"] == ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    assert got["monthly"] == [
        {
            "month": "2026-02",
            "score_psi": None,
            "auc": 0.81,
            "ks": 0.52,
            "rows": 90,
            "bad_rate": 0.04,
            "in_reference": True,
        },
        {
            "month": "2026-03",
            "score_psi": 0.01,
            "auc": 0.8,
            "ks": 0.5,
            "rows": 100,
            "bad_rate": 0.05,
            "in_reference": True,
        },
        {
            "month": "2026-04",
            "score_psi": 0.02,
            "auc": None,
            "ks": None,
            "rows": 100,
            "bad_rate": 0.06,
            "in_reference": True,
        },
        {
            "month": "2026-05",
            "score_psi": 0.12,
            "auc": 0.7,
            "ks": 0.35,
            "rows": 100,
            "bad_rate": 0.07,
            "in_reference": False,
        },
        # bad_rate None from the score run is kept rather than taken from model_ks.
        {
            "month": "2026-06",
            "score_psi": 0.31,
            "auc": None,
            "ks": None,
            "rows": 80,
            "bad_rate": None,
            "in_reference": False,
        },
    ]
    assert got["feature_psi"] == [
        {"name": "income", "label": {"zh": "月收入", "en": "Income"}, "values": [None, None, 0.0, 0.2, 0.4]},
        {"name": "c8", "label": {"zh": "年龄", "en": "年龄"}, "values": [None, None, 0.0, 0.01, 0.02]},
    ]
    assert (got["thresholds"], got["ks_thresholds"]) == (
        {"warn": 0.15, "alert": 0.3},
        {"warn": 0.1, "alert": 0.2},
    )
    assert got["reference"] == ["2026-03", "2026-04"]
    assert got["reference_metrics"] == {"auc": 0.8, "ks": 0.5, "labelled": 200}
    assert set(got["monitors"]) == {"score_psi", "model_ks", "indicator_psi"}
    assert got["monitors"]["score_psi"]["id"] == str(score.id)  # the enabled one
    assert [a["id"] for a in got["alerts"]] == [alert.id]

    # Another model on request; an unknown one falls back to the default.
    chosen = users.ana.get(f"{API}/stability", params={"model_id": str(old.id)}).json()
    assert chosen["model"]["code"] == "OLD_APP" and chosen["months"] == ["2025-04"]
    assert (chosen["feature_psi"], chosen["reference_metrics"], chosen["ks_thresholds"]) == (
        [],
        None,
        {"warn": 0.1, "alert": 0.2},
    )
    assert chosen["thresholds"] == {"warn": 0.2, "alert": 0.3} and chosen["reference"] == [
        "2025-01",
        "2025-03",
    ]
    assert list(chosen["monitors"]) == ["score_psi"] and len(chosen["alerts"]) == 1
    assert (
        users.ana.get(f"{API}/stability", params={"model_id": MISSING}).json()["model"]["code"]
        == "RETAIL_APP"
    )

    # Without an online model, the first monitored model.
    db.execute(ModelVersion.__table__.update().values(status="retired"))
    db.commit()
    assert users.ana.get(f"{API}/stability").json()["model"]["code"] == "OLD_APP"


# ---- Demo content ---------------------------------------------------------------------------------


def test_seed_monitors_is_idempotent(make_user, db):
    admin, analyst = make_user("root", Role.admin), make_user("analyst")
    assert seed_monitors(db, admin, analyst) == []  # nothing to watch yet
    seed_datasets(db, admin, as_of=date(2026, 11, 19))
    seed_model(db, admin, analyst)
    seed_strategy(db, admin, analyst)
    created = seed_monitors(db, admin, analyst)
    monitors = db.scalars(select(Monitor).order_by(Monitor.created_at)).unique().all()
    assert [m.kind for m in monitors] == [
        "score_psi",
        "model_ks",
        "indicator_psi",
        "approval_rate",
        "rule_hit_rate",
    ]
    assert created == [f"monitor {m.name}: {m.last_level}" for m in monitors]
    for m in monitors:
        assert m.owner_id == analyst.id and m.enabled and m.next_run_at > datetime.now(UTC)
        on_strategy = m.kind in ("approval_rate", "rule_hit_rate")
        assert (m.strategy.code if on_strategy else m.model.code) == (
            STRATEGY_CODE if on_strategy else MODEL_CODE
        )
        assert (m.dataset_id is None) == on_strategy
    runs = db.scalars(select(MonitorRun)).all()
    assert sorted(r.monitor_id for r in runs) == sorted(m.id for m in monitors)  # one run each
    assert {r.trigger for r in runs} == {"seed"}
    by_kind = {m.kind: m for m in monitors}
    status = {m.kind: next(r for r in runs if r.monitor_id == m.id) for m in monitors}
    assert all(status[k].status == "done" for k in ("score_psi", "model_ks", "indicator_psi"))
    # The demo decisions end on the seed date, so the decision checks need it to be recent.
    for kind in ("approval_rate", "rule_hit_rate"):
        assert status[kind].status == "done" or status[kind].code == "too_few_requests", kind
    assert by_kind["rule_hit_rate"].thresholds == {"warn": 0.03, "alert": 0.08}
    assert by_kind["approval_rate"].schedule == {"weekday": 0, "freq": "hourly", "minute": 5}
    assert all(by_kind[k].thresholds == DEFAULT_THRESHOLDS[k] for k in by_kind if k != "rule_hit_rate")

    # The simulated drift in credit inquiries raises an alert, already claimed by the analyst.
    features = by_kind["indicator_psi"]
    run_ = next(r for r in runs if r.monitor_id == features.id)
    assert run_.level == "alert" and run_.detail["worst"]["code"] == "inquiries_6m"
    alert = db.scalar(select(Alert).where(Alert.monitor_id == features.id))
    assert (alert.status, alert.level, alert.assignee_id) == ("acknowledged", "alert", analyst.id)
    assert alert.note and [e["action"] for e in alert.events] == ["opened", "acknowledged"]
    assert alert.detail["worst"]["code"] == "inquiries_6m"

    assert seed_monitors(db, admin, analyst) == []
    assert db.scalar(select(func.count()).select_from(Monitor)) == 5
    assert db.scalar(select(func.count()).select_from(MonitorRun)) == 5
    # Refreshing the demo takes its monitors with it.
    refresh(db)
    db.expire_all()
    for cls in (Monitor, MonitorRun, Alert):
        assert db.scalar(select(func.count()).select_from(cls)) == 0, cls.__name__


def test_training_reference_covering_every_month_falls_back_to_the_first_half():
    from kivi_ui.monitoring.checks import _reference

    months = [f"2026-{m:02d}" for m in range(1, 7)]
    # Trained on every month (no out-of-time months): the first half becomes the reference.
    assert _reference(months, {}, ["2026-01", "2026-06"]) == months[:3]
    # A training period that ends earlier is used as is.
    assert _reference(months, {}, ["2026-01", "2026-04"]) == months[:4]
