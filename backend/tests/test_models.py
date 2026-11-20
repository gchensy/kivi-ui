from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from conftest import loan_csv, loan_frame, upload
from sqlalchemy import func, select

from kivi_ui import jobs
from kivi_ui.analytics.training import score_frame
from kivi_ui.config import get_settings
from kivi_ui.data import store
from kivi_ui.demo import MODEL_CODE, seed_datasets, seed_model
from kivi_ui.models import AuditLog, Dataset, Job, ModelReview, ModelVersion, RiskModel, Role

API = "/api/v1"
FEATURE_COLUMNS = ["income", "city", "年龄", "responded"]
MISSING = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def users(make_user, login):
    """An analyst author, a second analyst and an administrator reviewer."""
    make_user("ana")
    make_user("bob")
    make_user("root", Role.admin)
    return SimpleNamespace(ana=login("ana"), bob=login("bob"), root=login("root"))


@pytest.fixture
def loans(users):
    dataset = upload(users.ana, loan_csv(rows=600)).json()
    response = users.ana.post(
        f"{API}/indicators/import", json={"dataset_id": dataset["id"], "columns": FEATURE_COLUMNS}
    )
    assert response.status_code == 201, response.json()
    return SimpleNamespace(dataset=dataset, indicators=response.json())


@pytest.fixture
def model(users):
    response = new_model(users.ana)
    assert response.status_code == 201, response.json()
    return response.json()


def new_model(c, code="retail_app", **fields):
    return c.post(f"{API}/models", json={"code": code, "name": "零售申请评分卡"} | fields)


def new_version(c, model, loans, *, indicators=None, dataset=None, notes="", **config):
    ids = [i["id"] for i in (loans.indicators if indicators is None else indicators)]
    body = {
        "dataset_id": (dataset or loans.dataset)["id"],
        "indicator_ids": ids,
        "config": config,
        "notes": notes,
    }
    return c.post(f"{API}/models/{model['id']}/versions", json=body)


def trained(c, model, loans, *, indicators=None, **config) -> dict:
    """Train a version through the queue and return its detail."""
    response = new_version(c, model, loans, indicators=indicators, **config)
    assert response.status_code == 201, response.json()
    assert jobs.run_pending() == 1
    return c.get(f"{API}/model-versions/{response.json()['id']}").json()


def act(c, version, action, comment=""):
    return c.post(f"{API}/model-versions/{version['id']}/{action}", json={"comment": comment})


def to_online(users, version) -> dict:
    """Author submits, administrator approves and takes the version online."""
    for c, action in ((users.ana, "submit"), (users.root, "approve"), (users.root, "online")):
        response = act(c, version, action)
        assert response.status_code == 200, response.json()
    return response.json()


# ---- Models ---------------------------------------------------------------------------------------


def test_create_list_and_update_models(users):
    response = new_model(users.ana, " retail_app ", name_en="Retail", scene="application")
    assert response.status_code == 201, response.json()
    created = response.json()
    assert (created["code"], created["name_en"], created["scene"]) == ("RETAIL_APP", "Retail", "application")
    assert created["owner"]["username"] == "ana"
    assert (created["version_count"], created["online"], created["latest"], created["versions"]) == (
        0,
        None,
        None,
        [],
    )

    taken = new_model(users.bob, "Retail_App")
    assert taken.status_code == 409 and taken.json()["code"] == "code_taken"
    for code in ("9lives", "x", "has space", "a-b"):
        assert new_model(users.ana, code).status_code == 422, code
    assert new_model(users.ana, "OTHER", scene="mortgage").status_code == 422
    assert new_model(users.ana, "OTHER", name="").status_code == 422

    listed = users.bob.get(f"{API}/models").json()
    assert [m["code"] for m in listed] == ["RETAIL_APP"]

    url = f"{API}/models/{created['id']}"
    assert users.bob.patch(url, json={"name": "x"}).json()["code"] == "forbidden"
    updated = users.ana.patch(url, json={"name": " 新名称 ", "scene": "behavior"}).json()
    assert (updated["name"], updated["scene"], updated["code"]) == ("新名称", "behavior", "RETAIL_APP")
    assert users.root.patch(url, json={"description": "admin edit"}).json()["description"] == "admin edit"
    assert users.ana.get(f"{API}/models/{MISSING}").json()["code"] == "model_not_found"


# ---- Training -------------------------------------------------------------------------------------


def test_train_a_version_in_the_background(users, loans, model, db):
    income = next(i for i in loans.indicators if i["code"] == "income")
    scheme = users.ana.post(
        f"{API}/indicators/{income['id']}/schemes",
        json={"name": "manual", "spec": {"method": "manual", "cuts": [8000, 12000]}},
    )
    assert scheme.status_code == 201, scheme.json()

    response = new_version(users.ana, model, loans, oot_months=2, notes=" first cut ")
    assert response.status_code == 201, response.json()
    queued = response.json()
    assert (queued["status"], queued["version"], queued["feature_count"]) == ("training", 1, 0)
    assert queued["auc_oot"] is None and queued["result"] == {} and queued["reviews"] == []
    assert queued["author"]["username"] == "ana" and queued["dataset"]["id"] == loans.dataset["id"]
    assert queued["model"]["code"] == "RETAIL_APP" and queued["notes"] == "first cut"
    assert queued["config"]["indicator_ids"] == [i["id"] for i in loans.indicators]
    assert queued["config"]["train"]["oot_months"] == 2 and queued["config"]["train"]["pdo"] == 50
    job = users.ana.get(f"{API}/jobs/{queued['job_id']}").json()
    assert (job["kind"], job["status"], job["started_at"]) == ("train_model", "queued", None)

    assert jobs.run_pending() == 1
    version = users.ana.get(f"{API}/model-versions/{queued['id']}").json()
    assert version["status"] == "draft" and version["error"] is None
    result = version["result"]
    assert version["feature_count"] == len(result["features"]) >= 1
    for split in ("train", "test", "oot"):
        assert version[f"auc_{split}"] == result["evaluation"][split]["roc"]["auc"]
        assert version[f"ks_{split}"] == result["evaluation"][split]["roc"]["ks"]
        assert 0.5 < version[f"auc_{split}"] <= 1
    assert result["evaluation"]["oot"]["period"] == ["2026-05", "2026-06"]
    codes = {i["code"]: i for i in loans.indicators}
    for feature in result["features"]:
        assert feature["indicator_id"] == codes[feature["code"]]["id"]

    job = users.ana.get(f"{API}/jobs/{queued['job_id']}").json()
    assert job["status"] == "done" and job["progress"] == 1
    assert job["result"] == {"version_id": version["id"], "features": version["feature_count"]}

    detail = users.bob.get(f"{API}/models/{model['id']}").json()
    assert detail["version_count"] == 1 and detail["latest"]["id"] == version["id"]
    assert detail["online"] is None and [v["status"] for v in detail["versions"]] == ["draft"]
    # Anyone may train a version; training bins each indicator with its default scheme.
    alone = trained(users.bob, model, loans, indicators=[income])
    assert alone["version"] == 2 and alone["author"]["username"] == "bob"
    [feature] = alone["result"]["features"]
    assert feature["spec"]["method"] == "manual" and feature["rule"]["cuts"] == [8000, 12000]
    assert [v["version"] for v in users.ana.get(f"{API}/models/{model['id']}").json()["versions"]] == [2, 1]
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "model")).all()
    assert sorted(actions) == ["model.created", "version.trained", "version.trained"]


def test_a_failed_training_marks_the_version(users, loans, model):
    weak = [i for i in loans.indicators if i["code"] in ("c8", "responded")]  # IV below 0.99
    version = trained(users.ana, model, loans, indicators=weak, iv_min=0.99)
    assert version["status"] == "failed" and version["feature_count"] == 0
    assert version["error"].startswith("no_features_left: ")
    job = users.ana.get(f"{API}/jobs/{version['job_id']}").json()
    assert job["status"] == "failed" and job["error"] == version["error"]

    scored = users.ana.post(
        f"{API}/model-versions/{version['id']}/score", json={"dataset_id": loans.dataset["id"]}
    )
    assert scored.status_code == 409 and scored.json()["code"] == "invalid_transition"
    assert act(users.ana, version, "submit").json()["code"] == "invalid_transition"
    assert users.ana.delete(f"{API}/model-versions/{version['id']}").status_code == 204


def test_a_deleted_indicator_or_tiny_sample_fails_cleanly(users, model):
    small = upload(users.ana, loan_csv(rows=80), name="small").json()
    [indicator] = users.ana.post(
        f"{API}/indicators/import", json={"dataset_id": small["id"], "columns": ["income"]}
    ).json()
    loans = SimpleNamespace(dataset=small, indicators=[indicator])
    assert trained(users.ana, model, loans)["error"].startswith("too_few_events: ")

    response = new_version(users.ana, model, loans)
    assert users.ana.delete(f"{API}/indicators/{indicator['id']}").status_code == 204
    assert jobs.run_pending() == 1
    gone = users.ana.get(f"{API}/model-versions/{response.json()['id']}").json()
    assert gone["status"] == "failed" and gone["error"].startswith("indicators_missing:")


def test_version_rejections(users, loans, model):
    other = upload(users.ana, loan_csv(rows=60), name="other").json()
    foreign = users.ana.post(
        f"{API}/indicators/import", json={"dataset_id": other["id"], "columns": ["income"]}
    ).json()
    response = new_version(users.ana, model, loans, indicators=[*loans.indicators, *foreign])
    assert response.status_code == 400 and response.json()["code"] == "invalid_indicators"
    assert response.json()["detail"] == {"codes": [foreign[0]["code"]]}
    unknown = new_version(users.ana, model, loans, indicators=[{"id": MISSING}])
    assert unknown.status_code == 400 and unknown.json()["code"] == "invalid_indicators"
    assert new_version(users.ana, model, loans, indicators=[]).status_code == 422
    assert new_version(users.ana, model, loans, test_ratio=0.9).status_code == 422
    assert new_version(users.ana, model, loans, dataset={"id": MISSING}).json()["code"] == "dataset_not_found"
    assert new_version(users.ana, {"id": MISSING}, loans).json()["code"] == "model_not_found"

    users.ana.patch(f"{API}/datasets/{loans.dataset['id']}", json={"clear": ["target_column"]})
    response = new_version(users.ana, model, loans)
    assert response.status_code == 400 and response.json()["code"] == "no_target"
    assert users.ana.get(f"{API}/models/{model['id']}").json()["version_count"] == 0
    assert users.ana.get(f"{API}/model-versions/{MISSING}").json()["code"] == "version_not_found"


# ---- Review lifecycle -----------------------------------------------------------------------------


def test_review_lifecycle(users, loans, model, db):
    version = trained(users.ana, model, loans)
    for action in ("approve", "reject", "online"):
        response = act(users.root, version, action)
        assert response.status_code == 409 and response.json()["code"] == "invalid_transition", action
        assert response.json()["detail"] == {"status": "draft"}
    assert act(users.root, version, "publish").status_code == 404
    assert act(users.bob, version, "submit").json()["code"] == "forbidden"  # not the author

    submitted = act(users.ana, version, "submit", " ready ").json()
    assert submitted["status"] == "in_review" and submitted["submitter"]["username"] == "ana"
    assert submitted["submitted_at"] is not None
    assert act(users.ana, version, "submit").status_code == 409
    assert act(users.ana, version, "approve").json()["code"] == "forbidden"
    assert act(users.bob, version, "reject").json()["code"] == "forbidden"

    rejected = act(users.root, version, "reject", "check the OOT drift").json()
    assert (
        rejected["status"] == "draft" and rejected["submitter"] is None and rejected["submitted_at"] is None
    )
    assert act(users.ana, version, "submit").json()["status"] == "in_review"
    approved = act(users.root, version, "approve", "ok").json()
    assert approved["status"] == "approved" and approved["approver"]["username"] == "root"
    assert act(users.root, version, "submit").status_code == 409
    assert act(users.ana, version, "online").json()["code"] == "forbidden"
    online = act(users.root, version, "online").json()
    assert online["status"] == "online" and online["online_at"] is not None

    reviews = [(r["action"], r["actor"]["username"], r["comment"]) for r in online["reviews"]]
    assert reviews == [
        ("submit", "ana", "ready"),
        ("reject", "root", "check the OOT drift"),
        ("submit", "ana", ""),
        ("approve", "root", "ok"),
        ("online", "root", ""),
    ]
    summary = users.bob.get(f"{API}/models").json()[0]
    assert summary["online"]["id"] == version["id"] and summary["latest"]["id"] == version["id"]

    retired = act(users.root, version, "retire", "end of life").json()
    assert retired["status"] == "retired" and retired["retired_at"] is not None
    for action in ("submit", "approve", "online", "retire"):
        assert act(users.root, version, action).status_code == 409, action
    assert users.bob.get(f"{API}/models").json()[0]["online"] is None
    actions = db.scalars(select(AuditLog.action).where(AuditLog.action.like("version.%"))).all()
    assert sorted(set(actions)) == [
        "version.approve",
        "version.online",
        "version.reject",
        "version.retire",
        "version.submit",
        "version.trained",
    ]


def test_four_eyes(users, loans, model, make_user, login, monkeypatch):
    version = trained(users.root, model, loans)
    assert act(users.root, version, "submit").json()["status"] == "in_review"
    blocked = act(users.root, version, "approve")
    assert blocked.status_code == 403 and blocked.json()["code"] == "four_eyes"
    assert act(users.ana, version, "approve").json()["code"] == "forbidden"
    make_user("rex", Role.admin)
    assert act(login("rex"), version, "approve").json()["status"] == "approved"

    # The author's own approval passes once the rule is switched off.
    second = trained(users.root, model, loans)
    assert act(users.root, second, "submit").status_code == 200
    assert act(users.root, second, "approve").json()["code"] == "four_eyes"
    monkeypatch.setenv("KIVI_REQUIRE_FOUR_EYES", "false")
    get_settings.cache_clear()
    approved = act(users.root, second, "approve").json()
    assert approved["status"] == "approved"
    assert approved["submitter"]["username"] == approved["approver"]["username"] == "root"


def test_taking_a_version_online_retires_the_previous_one(users, loans, model, db):
    first = to_online(users, trained(users.ana, model, loans))
    second = trained(users.ana, model, loans)
    assert act(users.ana, second, "submit").status_code == 200
    assert act(users.root, second, "approve").status_code == 200
    assert act(users.root, second, "online").json()["status"] == "online"

    first = users.ana.get(f"{API}/model-versions/{first['id']}").json()
    assert first["status"] == "retired" and first["retired_at"] is not None
    last = first["reviews"][-1]
    assert (last["action"], last["actor"]["username"], last["comment"]) == (
        "retire",
        "root",
        "replaced by v2",
    )
    assert users.ana.get(f"{API}/models/{model['id']}").json()["online"]["version"] == 2
    assert db.scalar(select(func.count()).where(ModelVersion.status == "online")) == 1

    # An approved version can be retired without ever going online.
    third = trained(users.ana, model, loans)
    act(users.ana, third, "submit")
    act(users.root, third, "approve")
    assert act(users.root, third, "retire").json()["status"] == "retired"
    assert users.ana.get(f"{API}/models/{model['id']}").json()["online"]["version"] == 2


def test_delete_rules(users, loans, model, db):
    online = to_online(users, trained(users.ana, model, loans))
    draft = trained(users.ana, model, loans)
    url = f"{API}/models/{model['id']}"

    blocked = users.ana.delete(url)
    assert blocked.status_code == 409 and blocked.json()["code"] == "model_online"
    refused = users.ana.delete(f"{API}/model-versions/{online['id']}")
    assert refused.status_code == 409 and refused.json()["code"] == "invalid_transition"
    assert users.bob.delete(f"{API}/model-versions/{draft['id']}").json()["code"] == "forbidden"
    assert users.ana.delete(f"{API}/model-versions/{draft['id']}").status_code == 204
    assert users.ana.get(f"{API}/model-versions/{draft['id']}").json()["code"] == "version_not_found"
    assert (
        users.root.delete(f"{API}/model-versions/{trained(users.ana, model, loans)['id']}").status_code == 204
    )

    assert act(users.root, online, "retire").status_code == 200
    assert users.bob.delete(url).json()["code"] == "forbidden"
    assert users.ana.delete(url).status_code == 204
    assert users.ana.get(url).json()["code"] == "model_not_found"
    assert db.scalar(select(func.count()).select_from(RiskModel)) == 0
    assert db.scalar(select(func.count()).select_from(ModelVersion)) == 0
    assert db.scalar(select(func.count()).select_from(ModelReview)) == 0
    assert db.scalar(select(func.count()).select_from(Job)) == 3  # the job history stays


# ---- Scoring --------------------------------------------------------------------------------------


def score(c, version, dataset):
    return c.post(f"{API}/model-versions/{version['id']}/score", json={"dataset_id": dataset["id"]})


def test_scoring_creates_a_score_dataset(users, loans, model, db):
    version = trained(users.ana, model, loans)
    response = score(users.bob, version, loans.dataset)
    assert response.status_code == 202, response.json()
    job = response.json()
    assert (job["kind"], job["status"]) == ("score_dataset", "queued")
    assert jobs.run_pending() == 1
    job = users.bob.get(f"{API}/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    assert job["result"]["rows"] == 600

    scored = users.bob.get(f"{API}/datasets/{job['result']['dataset_id']}").json()
    assert scored["source"] == "score" and scored["owner"]["username"] == "bob"
    assert scored["name"] == "RETAIL_APP v1 · loans" and scored["row_count"] == 600
    columns = {c["column_name"]: c for c in scored["columns"]}
    assert list(columns) == ["id", "apply_date", "target", "score", "probability"]
    assert (scored["target_column"], scored["date_column"], scored["id_column"]) == (
        "target",
        "apply_date",
        "id",
    )
    assert scored["bad_rate"] == pytest.approx(loans.dataset["bad_rate"])
    assert columns["score"]["dtype"] == columns["probability"]["dtype"] == "numeric"

    # The stored scores are the version's scorecard applied to the source rows.
    source = db.get(Dataset, loans.dataset["id"])
    features = [f["column"] for f in version["result"]["features"]]
    expected = pd.concat(
        [
            store.read_columns(db, source, ["id", *features]),
            score_frame(version["result"], store.read_columns(db, source, features)),
        ],
        axis=1,
    )
    stored = store.read_columns(db, db.get(Dataset, scored["id"]), ["id", "score", "probability"])
    merged = stored.astype({"id": int}).merge(expected, on="id", suffixes=("", "_expected"))
    assert len(merged) == 600
    assert (merged.score == merged.score_expected).all()
    assert merged.probability.to_numpy() == pytest.approx(merged.probability_expected.to_numpy(), abs=1e-6)


def test_scoring_needs_the_model_columns(users, loans, model, db):
    version = trained(users.ana, model, loans)
    lacking = upload(
        users.ana, loan_frame(rows=60).drop(columns=["income"]).to_csv(index=False).encode(), name="lacking"
    )
    job = score(users.ana, version, lacking.json()).json()
    before = db.scalar(select(func.count()).select_from(Dataset))
    assert jobs.run_pending() == 1
    job = users.ana.get(f"{API}/jobs/{job['id']}").json()
    assert job["status"] == "failed" and job["error"].startswith("missing_columns: the dataset lacks ")
    assert "income" in job["error"]
    assert db.scalar(select(func.count()).select_from(Dataset)) == before

    training = new_version(users.ana, model, loans).json()
    assert score(users.ana, training, loans.dataset).json()["code"] == "invalid_transition"
    assert score(users.ana, version, {"id": MISSING}).json()["code"] == "dataset_not_found"
    assert score(users.ana, {"id": MISSING}, loans.dataset).json()["code"] == "version_not_found"


def test_scoring_keeps_a_chinese_target_header(users, model):
    frame = loan_frame(rows=600).rename(columns={"target": "是否违约", "id": "编号"})
    dataset = upload(users.ana, frame.to_csv(index=False).encode()).json()
    assert dataset["target_column"] == "c5"
    indicators = users.ana.post(
        f"{API}/indicators/import", json={"dataset_id": dataset["id"], "columns": ["income", "city"]}
    ).json()
    version = trained(users.ana, model, SimpleNamespace(dataset=dataset, indicators=indicators))
    job = score(users.ana, version, dataset).json()
    assert jobs.run_pending() == 1
    job = users.ana.get(f"{API}/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    scored = users.ana.get(f"{API}/datasets/{job['result']['dataset_id']}").json()
    target = next(c for c in scored["columns"] if c["name"] == "是否违约")
    assert scored["target_column"] == target["column_name"] and target["role"] == "target"
    assert scored["bad_rate"] == pytest.approx(dataset["bad_rate"])


# ---- Jobs and access ------------------------------------------------------------------------------


def test_job_visibility(users, loans, model):
    response = new_version(users.ana, model, loans)
    url = f"{API}/jobs/{response.json()['job_id']}"
    assert users.ana.get(url).status_code == 200
    assert users.root.get(url).status_code == 200
    hidden = users.bob.get(url)
    assert hidden.status_code == 404 and hidden.json()["code"] == "job_not_found"
    assert users.root.get(f"{API}/jobs/{MISSING}").json()["code"] == "job_not_found"


def test_models_require_sign_in(anon):
    model, version = f"{API}/models/{MISSING}", f"{API}/model-versions/{MISSING}"
    for response in (
        anon.get(f"{API}/models"),
        anon.post(f"{API}/models", json={"code": "X1", "name": "x"}),
        anon.get(model),
        anon.patch(model, json={"name": "x"}),
        anon.delete(model),
        anon.post(f"{model}/versions", json={"dataset_id": MISSING, "indicator_ids": [MISSING]}),
        anon.get(version),
        anon.delete(version),
        anon.post(f"{version}/score", json={"dataset_id": MISSING}),
        anon.post(f"{version}/submit", json={}),
        anon.get(f"{API}/jobs/{MISSING}"),
    ):
        assert response.status_code == 401 and response.json()["code"] == "unauthenticated"


# ---- Demo -----------------------------------------------------------------------------------------


def test_seed_model_is_idempotent(make_user, db, login):
    admin, analyst = make_user("root", Role.admin), make_user("analyst")
    assert seed_model(db, admin, analyst) == []  # no demo data yet
    seed_datasets(db, admin, as_of=date(2026, 11, 19))
    [message] = seed_model(db, admin, analyst)
    assert message.startswith(f"model {MODEL_CODE} v1 online (OOT AUC 0.")

    model = db.scalar(select(RiskModel))
    [version] = model.versions
    assert (model.code, model.owner_id, version.status) == (MODEL_CODE, analyst.id, "online")
    assert version.created_by == version.submitted_by == analyst.id and version.approved_by == admin.id
    assert version.feature_count == len(version.result["features"]) > 3
    assert 0.6 < version.auc_oot < 0.9 and version.ks_oot > 0
    # The three reviews share one transaction timestamp, so their order is not asserted.
    assert sorted(r.action for r in version.reviews) == ["approve", "online", "submit"]
    job = db.get(Job, version.job_id)
    assert job.status == "done" and job.result["features"] == version.feature_count

    assert seed_model(db, admin, analyst) == []
    assert db.scalar(select(func.count()).select_from(RiskModel)) == 1
    assert db.scalar(select(func.count()).select_from(ModelVersion)) == 1
    summary = login("analyst").get(f"{API}/models").json()
    assert [(m["code"], m["online"]["version"]) for m in summary] == [(MODEL_CODE, 1)]


def test_author_cannot_approve_even_when_another_admin_submitted(make_user, login, monkeypatch):
    """Four eyes covers the maker as well as the submitter."""
    from kivi_ui.models import ModelVersion

    author = make_user("author1", Role.admin)
    make_user("submitter1", Role.admin)
    admin = login("author1")
    other = login("submitter1")
    model = admin.post("/api/v1/models", json={"code": "eyes", "name": "eyes"}).json()
    from kivi_ui.db import get_sessionmaker

    with get_sessionmaker()() as db:
        version = ModelVersion(
            model_id=model["id"], version=1, status="draft", created_by=author.id, config={}, result={}
        )
        db.add(version)
        db.commit()
        version_id = str(version.id)
    assert other.post(f"/api/v1/model-versions/{version_id}/submit", json={}).status_code == 200
    blocked = admin.post(f"/api/v1/model-versions/{version_id}/approve", json={})
    assert blocked.status_code == 403 and blocked.json()["code"] == "four_eyes"
    third = make_user("checker1", Role.admin)
    assert (
        third
        and login("checker1").post(f"/api/v1/model-versions/{version_id}/approve", json={}).status_code == 200
    )


def test_non_admin_gets_forbidden_before_state_checks(make_user, login):
    from kivi_ui.db import get_sessionmaker
    from kivi_ui.models import ModelVersion

    owner = make_user("ana2")
    analyst = login("ana2")
    model = analyst.post("/api/v1/models", json={"code": "roles", "name": "roles"}).json()
    with get_sessionmaker()() as db:
        version = ModelVersion(
            model_id=model["id"], version=1, status="draft", created_by=owner.id, config={}, result={}
        )
        db.add(version)
        db.commit()
        version_id = str(version.id)
    response = analyst.post(f"/api/v1/model-versions/{version_id}/online", json={})
    assert response.status_code == 403 and response.json()["code"] == "forbidden"
