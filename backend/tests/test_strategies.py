"""Strategies, watchlists, API tokens, the decision API and its log, and the demo strategy."""

import functools
import hashlib
import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from conftest import loan_csv, loan_frame, upload
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from kivi_ui import jobs
from kivi_ui.config import get_settings
from kivi_ui.data import store
from kivi_ui.demo import (
    BLACKLIST,
    RETAIL,
    STRATEGY_CODE,
    WHITELIST,
    refresh,
    seed_datasets,
    seed_model,
    seed_strategy,
)
from kivi_ui.main import create_app
from kivi_ui.models import (
    ApiToken,
    AuditLog,
    Dataset,
    DecisionLog,
    ModelVersion,
    RiskList,
    RiskListItem,
    RiskModel,
    Role,
    Strategy,
    StrategyReview,
    StrategyVersion,
)
from kivi_ui.rules import runtime
from kivi_ui.rules.engine import normalise_value

API = "/api/v1"
MISSING = "00000000-0000-0000-0000-000000000000"
CODE = "RETAIL_APPLY"


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
    """Two analysts (ana is the usual author) and two administrators."""
    for name, role in (
        ("ana", Role.analyst),
        ("bob", Role.analyst),
        ("root", Role.admin),
        ("rex", Role.admin),
    ):
        make_user(name, role)
    return Sessions(login)


# ---- Helpers ------------------------------------------------------------------------------------


def cond(field, op, value=None) -> dict:
    return {"field": field, "op": op, "value": value}


def rule(code, *items, decision="reject", mode="all", **extra) -> dict:
    when = {"mode": mode, "items": list(items)}
    return {"code": code, "name": f"rule {code}", "decision": decision, "when": when} | extra


def definition(*rules, default="pass") -> dict:
    return {"default_decision": default, "rules": list(rules)}


# Whitelist first, then the blacklist, an age band and a review rule without a reason.
SIMPLE = (
    rule("W01", cond("phone", "in_list", "WL_PHONE"), decision="pass", terminal=True, reason="WHITELIST"),
    rule("R01", cond("phone", "in_list", "BL_PHONE"), reason="BLACKLIST"),
    rule("R02", cond("age", "lt", 22), cond("age", "gt", 60), mode="any", reason="AGE"),
    rule("V01", cond("income", "lt", 5000), decision="review"),
)
BLACK = {"phone": "13800001234", "age": 30, "income": 9000}
WHITE = {"phone": "13800005678", "age": 30, "income": 9000}  # on both lists
YOUNG = {"phone": "13700000000", "age": 19, "income": 3000}
LOW = {"phone": "13700000000", "age": 30, "income": 3000}
GOOD = {"phone": "13700000000", "age": 30, "income": 9000}


def new_strategy(c, code="retail_apply", **fields):
    return c.post(f"{API}/strategies", json={"code": code, "name": "零售准入策略"} | fields)


def first_draft(c, code="retail_apply") -> tuple[dict, dict]:
    response = new_strategy(c, code)
    assert response.status_code == 201, response.json()
    strategy = response.json()
    return strategy, strategy["versions"][0]


def put(c, version, *rules, default="pass", notes=None):
    body = {"definition": definition(*rules, default=default)}
    if notes is not None:
        body["notes"] = notes
    return c.put(f"{API}/strategy-versions/{version['id']}", json=body)


def act(c, version, action, comment=""):
    return c.post(f"{API}/strategy-versions/{version['id']}/{action}", json={"comment": comment})


def to_online(users, version, author=None) -> dict:
    """The author submits, root approves and puts the version online."""
    for c, action in ((author or users.ana, "submit"), (users.root, "approve"), (users.root, "online")):
        response = act(c, version, action)
        assert response.status_code == 200, (action, response.json())
    return response.json()


def get_version(c, version) -> dict:
    return c.get(f"{API}/strategy-versions/{version['id']}").json()


def new_list(c, code="bl_phone", **fields):
    return c.post(f"{API}/risk-lists", json={"code": code, "name": "电话黑名单"} | fields)


def add_items(c, lst, *values, **fields):
    return c.post(f"{API}/risk-lists/{lst['id']}/items", json={"values": list(values)} | fields)


def check(c, lst, value):
    return c.post(f"{API}/risk-lists/{lst['id']}/check", json={"value": value}).json()


@functools.cache
def machine() -> TestClient:
    """A machine caller: no session cookie and no X-Requested-With header."""
    return TestClient(create_app())


def make_token(c, **fields) -> dict:
    response = c.post(f"{API}/api-tokens", json={"name": "gateway"} | fields)
    assert response.status_code == 201, response.json()
    return response.json()


def decide(token, data, *, code=CODE, request_id=None, client=None):
    body = {"data": data} | ({"request_id": request_id} if request_id else {})
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return (client or machine()).post(f"{API}/decide/{code}", json=body, headers=headers)


def console(c, version, data):
    return c.post(f"{API}/strategy-versions/{version['id']}/evaluate", json={"data": data})


@pytest.fixture
def lists(users):
    black = new_list(users.ana).json()
    white = new_list(users.ana, "wl_phone", kind="white", name="白名单").json()
    assert add_items(users.ana, black, "13800001234", "13800005678").json()["added"] == 2
    assert add_items(users.ana, white, "13900000000", "13800005678").json()["added"] == 2
    return SimpleNamespace(black=black, white=white)


@pytest.fixture
def online(users, lists):
    """RETAIL_APPLY v1 with the SIMPLE rules, online."""
    strategy, v1 = first_draft(users.ana)
    assert put(users.ana, v1, *SIMPLE).status_code == 200
    return SimpleNamespace(strategy=strategy, version=to_online(users, v1))


@pytest.fixture
def token(users) -> str:
    return make_token(users.root)["token"]


@pytest.fixture
def retail_model(users):
    """RETAIL_APP trained on the loan sample (income, city, 年龄, responded), online."""
    dataset = upload(users.ana, loan_csv(rows=600), name="train").json()
    indicators = users.ana.post(
        f"{API}/indicators/import",
        json={"dataset_id": dataset["id"], "columns": ["income", "city", "年龄", "responded"]},
    ).json()
    model = users.ana.post(f"{API}/models", json={"code": "retail_app", "name": "零售申请评分卡"}).json()
    body = {"dataset_id": dataset["id"], "indicator_ids": [i["id"] for i in indicators], "config": {}}
    version = users.ana.post(f"{API}/models/{model['id']}/versions", json=body).json()
    assert jobs.run_pending() == 1
    for c, action in ((users.ana, "submit"), (users.root, "approve"), (users.root, "online")):
        response = c.post(f"{API}/model-versions/{version['id']}/{action}", json={"comment": ""})
        assert response.status_code == 200, response.json()
    version = response.json()
    assert version["feature_count"] >= 2
    return SimpleNamespace(dataset=dataset, model=model, version=version)


# ---- Watchlists -----------------------------------------------------------------------------------


def test_create_update_and_list_watchlists(users):
    response = new_list(users.ana, " bl_phone ", name_en="Blacklist", description="fraud")
    assert response.status_code == 201, response.json()
    black = response.json()
    assert (black["code"], black["kind"], black["dimension"], black["name_en"]) == (
        "BL_PHONE",
        "black",
        "phone",
        "Blacklist",
    )
    assert black["owner"]["username"] == "ana" and (black["item_count"], black["active_count"]) == (0, 0)
    taken = new_list(users.bob, "Bl_Phone")
    assert taken.status_code == 409 and taken.json()["code"] == "code_taken"
    for bad in ({"code": "1x"}, {"code": "x"}, {"kind": "purple"}, {"dimension": "email"}, {"name": ""}):
        assert new_list(users.ana, **({"code": "OTHER"} | bad)).status_code == 422, bad
    new_list(users.bob, "id_white", kind="white", dimension="id_no")
    assert [x["code"] for x in users.bob.get(f"{API}/risk-lists").json()] == ["BL_PHONE", "ID_WHITE"]

    url = f"{API}/risk-lists/{black['id']}"
    assert users.bob.patch(url, json={"name": "x"}).json()["code"] == "forbidden"
    updated = users.ana.patch(url, json={"name": " 黑名单 ", "kind": "gray"}).json()
    assert (updated["name"], updated["kind"], updated["code"]) == ("黑名单", "gray", "BL_PHONE")
    assert users.root.patch(url, json={"description": "admin"}).json()["description"] == "admin"
    assert users.ana.patch(url, json={"code": "NEW"}).json()["code"] == "BL_PHONE"  # codes are fixed
    assert users.ana.get(url).json()["name"] == "黑名单"
    assert users.ana.get(f"{API}/risk-lists/{MISSING}").json()["code"] == "list_not_found"

    assert users.bob.delete(url).json()["code"] == "forbidden"
    assert users.root.delete(url).status_code == 204
    assert users.ana.get(url).status_code == 404


def test_watchlist_items_are_normalised_and_stored_as_digests(users, db):
    black = new_list(users.ana).json()
    url = f"{API}/risk-lists/{black['id']}"
    raw = ["13800001234", " 13800001234 ", "", "   ", "abc-1", "ABC-1", "13900005678"]
    # Any signed-in user maintains list entries; only the owner or an admin edits the list itself.
    added = add_items(users.bob, black, *raw, reason=" fraud ")
    assert added.status_code == 201 and added.json() == {"added": 3, "skipped": 4}
    assert add_items(users.ana, black, "13800001234", "15000000000").json() == {"added": 1, "skipped": 1}
    assert add_items(users.ana, black).status_code == 422

    page = users.ana.get(f"{url}/items").json()
    assert page["total"] == 4
    assert {i["value_masked"] for i in page["items"]} == {
        "138****1234",
        "A**1",
        "139****5678",
        "150****0000",
    }
    by_mask = {i["value_masked"]: i for i in page["items"]}
    assert by_mask["A**1"]["reason"] == "fraud" and by_mask["A**1"]["author"]["username"] == "bob"
    assert by_mask["150****0000"]["reason"] == "" and by_mask["150****0000"]["expires_at"] is None
    assert users.ana.get(url).json()["item_count"] == 4

    # Search and check match the normalised value exactly (by digest), never a prefix.
    for q, expected in ((" 13800001234 ", ["138****1234"]), ("abc-1", ["A**1"]), ("1380000", []), ("x", [])):
        found = users.ana.get(f"{url}/items", params={"q": q}).json()
        assert [i["value_masked"] for i in found["items"]] == expected and found["total"] == len(expected), q
    assert len(users.ana.get(f"{url}/items", params={"size": 3}).json()["items"]) == 3
    assert [
        i["id"] for i in users.ana.get(f"{url}/items", params={"size": 3, "page": 2}).json()["items"]
    ] == [min(i["id"] for i in page["items"])]
    listed = check(users.bob, black, " Abc-1 ")
    assert listed["listed"] is True and listed["item"]["value_masked"] == "A**1"
    assert check(users.bob, black, "13700000000") == {"listed": False, "item": None}
    assert check(users.bob, black, "   ") == {"listed": False, "item": None}

    # Expired entries stay visible but no longer match.
    now = datetime.now(UTC)
    past, future = (now - timedelta(hours=1)).isoformat(), (now + timedelta(days=1)).isoformat()
    assert add_items(users.ana, black, "18600000000", expires_at=past).json()["added"] == 1
    assert add_items(users.ana, black, "18700000000", expires_at=future).json()["added"] == 1
    assert check(users.ana, black, "18600000000")["listed"] is False
    assert check(users.ana, black, "18700000000")["item"]["expires_at"] is not None
    counts = users.ana.get(url).json()
    assert (counts["item_count"], counts["active_count"]) == (6, 5)
    assert users.ana.get(f"{url}/items").json()["total"] == 6
    digest = runtime.hasher()
    loaded = runtime.load_lists(db, {"BL_PHONE", "NOPE"})
    assert set(loaded) == {"BL_PHONE"} and len(loaded["BL_PHONE"]) == 5
    assert digest("18700000000") in loaded["BL_PHONE"] and digest("18600000000") not in loaded["BL_PHONE"]
    assert runtime.load_lists(db, set()) == {}

    # Only keyed digests and masked text reach the database (and the audit trail).
    plain = ["13800001234", "ABC-1", "abc-1", "ABC1", "13900005678"]
    plain += ["15000000000", "18600000000", "18700000000"]
    rows = db.scalars(select(RiskListItem)).all()
    assert {r.value_hash for r in rows} == {
        digest(t) for t in ("13800001234", "ABC1", "13900005678", "15000000000", "18600000000", "18700000000")
    }
    stored = json.dumps([[r.value_hash, r.value_masked, r.reason] for r in rows])
    stored += json.dumps([a.detail for a in db.scalars(select(AuditLog)).all()])
    assert not any(value in stored for value in plain)
    assert all(len(r.value_hash) == 64 and "*" in r.value_masked for r in rows)

    # Removing an entry.
    item = by_mask["139****5678"]
    other = new_list(users.ana, "other").json()
    assert (
        users.bob.delete(f"{API}/risk-lists/{other['id']}/items/{item['id']}").json()["code"]
        == "item_not_found"
    )
    assert users.bob.delete(f"{url}/items/{item['id']}").status_code == 204
    assert users.bob.delete(f"{url}/items/{item['id']}").json()["code"] == "item_not_found"
    assert check(users.ana, black, "13900005678")["listed"] is False
    assert users.ana.get(url).json()["item_count"] == 5
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "list")).all()
    assert sorted(set(actions)) == ["list.created", "list.item_removed", "list.items_added"]


def test_watchlists_require_sign_in(anon):
    url = f"{API}/risk-lists/{MISSING}"
    for response in (
        anon.get(f"{API}/risk-lists"),
        anon.post(f"{API}/risk-lists", json={"code": "BL", "name": "x"}),
        anon.get(url),
        anon.patch(url, json={"name": "x"}),
        anon.delete(url),
        anon.get(f"{url}/items"),
        anon.post(f"{url}/items", json={"values": ["1"]}),
        anon.delete(f"{url}/items/1"),
        anon.post(f"{url}/check", json={"value": "1"}),
    ):
        assert response.status_code == 401 and response.json()["code"] == "unauthenticated"


# ---- Strategies and versions --------------------------------------------------------------------


def test_creating_a_strategy_starts_an_empty_draft(users, db):
    response = new_strategy(users.ana, " retail_apply ", name_en="Retail admission", scene="fraud")
    assert response.status_code == 201, response.json()
    created = response.json()
    assert (created["code"], created["scene"], created["name_en"]) == (CODE, "fraud", "Retail admission")
    assert (
        created["owner"]["username"] == "ana" and created["version_count"] == 1 and created["online"] is None
    )
    [v1] = created["versions"]
    assert created["latest"]["id"] == v1["id"]
    assert (v1["version"], v1["status"], v1["rule_count"], v1["pass_rate"]) == (1, "draft", 0, None)
    detail = get_version(users.bob, v1)
    assert detail["definition"] == {"default_decision": "pass", "rules": []} and detail["backtest"] == {}
    assert detail["author"]["username"] == "ana" and detail["strategy"]["code"] == CODE
    assert detail["reviews"] == [] and detail["submitter"] is None

    taken = new_strategy(users.bob, "Retail_Apply")
    assert taken.status_code == 409 and taken.json()["code"] == "code_taken"
    for bad in ({"code": "9x"}, {"code": "has space"}, {"scene": "mortgage"}, {"name": ""}):
        assert new_strategy(users.ana, **({"code": "OTHER"} | bad)).status_code == 422, bad
    assert [s["code"] for s in users.bob.get(f"{API}/strategies").json()] == [CODE]

    url = f"{API}/strategies/{created['id']}"
    assert users.bob.patch(url, json={"name": "x"}).json()["code"] == "forbidden"
    updated = users.ana.patch(url, json={"name": " 新名称 ", "description": "admission"}).json()
    assert (updated["name"], updated["description"], updated["code"]) == ("新名称", "admission", CODE)
    assert users.root.patch(url, json={"scene": "limit"}).json()["scene"] == "limit"
    assert users.ana.get(f"{API}/strategies/{MISSING}").json()["code"] == "strategy_not_found"
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "strategy")).all()
    assert sorted(actions) == ["strategy.created", "strategy.updated", "strategy.updated"]


def test_fields_for_the_rule_editor(users, retail_model, lists):
    # A model without an online version offers no outputs.
    users.ana.post(f"{API}/models", json={"code": "draft_only", "name": "草稿模型"})
    dataset = retail_model.dataset
    out = users.bob.get(f"{API}/strategies/fields", params={"dataset_id": dataset["id"]}).json()
    by_name = {f["name"]: f for f in out["fields"]}
    for name in ("income", "city", "c8", "responded"):
        assert by_name[name]["source"] == "indicator", name
    assert by_name["c8"]["label"] == "年龄"
    for name in ("id", "apply_date", "outcome"):
        assert by_name[name]["source"] == "column", name
    assert by_name["apply_date"]["dtype"] == "datetime" and by_name["outcome"]["label"] == "outcome"
    assert "target" not in by_name
    assert by_name["model:RETAIL_APP.score"] == {
        "name": "model:RETAIL_APP.score",
        "label": "零售申请评分卡 · score",
        "dtype": "numeric",
        "source": "model",
    }
    assert by_name["model:RETAIL_APP.prob"]["source"] == "model"
    assert not any(name.startswith("model:DRAFT_ONLY") for name in by_name)
    assert out["models"] == [{"code": "RETAIL_APP", "name": "零售申请评分卡", "name_en": None, "version": 1}]
    assert [(x["code"], x["kind"], x["dimension"]) for x in out["lists"]] == [
        ("BL_PHONE", "black", "phone"),
        ("WL_PHONE", "white", "phone"),
    ]

    plain = {f["name"] for f in users.bob.get(f"{API}/strategies/fields").json()["fields"]}
    assert "apply_date" not in plain and {"income", "model:RETAIL_APP.score"} <= plain
    missing = users.bob.get(f"{API}/strategies/fields", params={"dataset_id": MISSING})
    assert missing.status_code == 404 and missing.json()["code"] == "dataset_not_found"


def test_rules_are_edited_on_drafts_by_their_author(users, lists, db):
    _, v1 = first_draft(users.ana)
    for bad in (
        [rule("R01", cond("age", "gt", "x"))],
        [rule("R01", cond("age", "gt", 1)), rule("R01", cond("age", "lt", 1))],
        [rule("R01", cond("age", "gt", 1)) | {"then": "reject"}],
        [rule("R01", {"mode": "all", "items": [cond("age", "between", [1])]})],
    ):
        response = put(users.ana, v1, *bad)
        assert response.status_code == 422 and response.json()["code"] == "validation_error", bad
    assert put(users.bob, v1, *SIMPLE).json()["code"] == "forbidden"  # not the author

    saved = put(
        users.ana, v1, *SIMPLE, rule("B01", cond("age", "between", [60, 18])), default="review", notes=" v1 "
    )
    assert saved.status_code == 200, saved.json()
    saved = saved.json()
    assert saved["rule_count"] == 5 and saved["notes"] == "v1"
    assert saved["definition"]["default_decision"] == "review"
    assert saved["definition"]["rules"][-1]["when"]["items"][0]["value"] == [18.0, 60.0]
    assert saved["definition"]["rules"][0] == {
        "code": "W01",
        "name": "rule W01",
        "name_en": None,
        "enabled": True,
        "decision": "pass",
        "terminal": True,
        "reason": "WHITELIST",
        "when": {"mode": "all", "items": [{"field": "phone", "op": "in_list", "value": "WL_PHONE"}]},
    }
    by_admin = put(users.root, v1, *SIMPLE).json()
    assert by_admin["rule_count"] == 4 and by_admin["notes"] == "v1"  # notes are kept when omitted

    assert act(users.ana, v1, "submit").status_code == 200
    refused = put(users.ana, v1, *SIMPLE)
    assert refused.status_code == 409 and refused.json()["code"] == "invalid_transition"
    assert users.ana.delete(f"{API}/strategy-versions/{v1['id']}").json()["code"] == "invalid_transition"
    assert users.ana.put(f"{API}/strategy-versions/{MISSING}", json={"definition": {}}).status_code == 404
    assert users.ana.get(f"{API}/strategy-versions/{MISSING}").json()["code"] == "version_not_found"


def test_new_versions_copy_rules(users, lists):
    strategy, v1 = first_draft(users.ana)
    put(users.ana, v1, *SIMPLE[:2])
    url = f"{API}/strategies/{strategy['id']}/versions"

    v2 = users.bob.post(url, json={"notes": " copy "}).json()  # anyone may branch a new version
    assert (v2["version"], v2["status"], v2["notes"], v2["author"]["username"]) == (2, "draft", "copy", "bob")
    assert v2["definition"] == get_version(users.ana, v1)["definition"] and v2["backtest"] == {}
    assert put(users.ana, v2, *SIMPLE).json()["code"] == "forbidden"  # the strategy owner is not its author
    assert put(users.bob, v2, *SIMPLE).json()["rule_count"] == 4

    v3 = users.ana.post(url, json={"copy_from": v1["id"]}).json()
    assert v3["version"] == 3 and len(v3["definition"]["rules"]) == 2
    v4 = users.ana.post(url, json={"definition": definition(SIMPLE[3], default="reject")}).json()
    assert v4["definition"]["default_decision"] == "reject" and v4["rule_count"] == 1
    v5 = users.ana.post(url, json={}).json()  # neither: a copy of the latest version
    assert v5["version"] == 5 and v5["definition"] == v4["definition"]

    _, foreign = first_draft(users.ana, "other")
    refused = users.ana.post(url, json={"copy_from": foreign["id"]})
    assert refused.status_code == 400 and refused.json()["code"] == "version_not_found"
    assert users.ana.post(url, json={"copy_from": MISSING}).json()["code"] == "version_not_found"
    bad = users.ana.post(url, json={"definition": definition(rule("X", cond("a", "in", [])))})
    assert bad.status_code == 422
    assert (
        users.ana.post(f"{API}/strategies/{MISSING}/versions", json={}).json()["code"] == "strategy_not_found"
    )

    listed = users.ana.get(f"{API}/strategies/{strategy['id']}").json()
    assert [v["version"] for v in listed["versions"]] == [5, 4, 3, 2, 1]
    assert listed["latest"]["version"] == 5 and listed["version_count"] == 5
    assert users.bob.delete(f"{API}/strategy-versions/{v5['id']}").json()["code"] == "forbidden"
    assert users.ana.delete(f"{API}/strategy-versions/{v5['id']}").status_code == 204
    assert users.root.delete(f"{API}/strategy-versions/{v2['id']}").status_code == 204
    assert [v["version"] for v in users.ana.get(f"{API}/strategies/{strategy['id']}").json()["versions"]] == [
        4,
        3,
        1,
    ]
    # Numbers are not reused once the latest is gone.
    assert users.ana.post(url, json={}).json()["version"] == 5


# ---- Backtests and the test console ------------------------------------------------------------

V1_RULES = (
    rule("R01", cond("income", "lt", 6000)),
    rule("R02", cond("city", "eq", "east"), decision="review"),
    rule("R03", cond("年龄", "lt", 25)),  # the uploaded header works as well as the SQL name
    rule("R04", cond("income", "is_null"), decision="review"),
)


def expected_decisions(frame: pd.DataFrame, income_cut: float) -> pd.Series:
    reject = (frame.income < income_cut) | (frame["年龄"] < 25)
    review = (frame.city == "east") | frame.income.isna()
    return pd.Series(np.where(reject, "reject", np.where(review, "review", "pass")), index=frame.index)


def test_backtest_on_an_uploaded_dataset(users, db):
    frame = loan_frame(rows=240)
    frame.loc[::8, "target"] = np.nan  # 30 rows without a label
    labelled = frame.target.notna()
    dataset = upload(users.ana, frame.to_csv(index=False).encode()).json()
    assert (dataset["target_column"], dataset["date_column"]) == ("target", "apply_date")
    strategy, v1 = first_draft(users.ana)
    put(users.ana, v1, *V1_RULES)

    response = users.bob.post(
        f"{API}/strategy-versions/{v1['id']}/backtest", json={"dataset_id": dataset["id"]}
    )
    assert response.status_code == 200, response.json()
    done = response.json()
    backtest = done["backtest"]
    assert backtest["dataset"] == {"id": dataset["id"], "name": "loans"} and "compare" not in backtest
    assert backtest["seconds"] >= 0 and backtest["ran_at"]
    summary = backtest["summary"]
    decisions = expected_decisions(frame, 6000)
    assert summary["rows"] == 240 and summary["missing_fields"] == []
    for d in ("pass", "review", "reject"):
        assert summary[d] == (decisions == d).sum() > 0, d
        assert summary[f"{d}_rate"] == pytest.approx((decisions == d).mean(), abs=1e-6)
        assert summary["bad_rate_by_decision"][d] == pytest.approx(
            frame.target[decisions == d].mean(), abs=1e-6
        )
    assert summary["pass"] + summary["review"] + summary["reject"] == 240
    assert summary["pass_rate"] + summary["review_rate"] + summary["reject_rate"] == pytest.approx(
        1, abs=1e-5
    )
    assert summary["bad_rate"] == pytest.approx(frame.target.mean(), abs=1e-6)
    hits = {r["code"]: r["hits"] for r in summary["rules"]}
    assert hits == {
        "R01": (frame.income < 6000).sum(),
        "R02": (frame.city == "east").sum(),
        "R03": (frame["年龄"] < 25).sum(),
        "R04": frame.income.isna().sum(),
    }
    assert [m["month"] for m in summary["monthly"]] == [f"2026-{m:02d}" for m in range(1, 7)]
    assert sum(m["rows"] for m in summary["monthly"]) == 240
    assert done["pass_rate"] == summary["pass_rate"]
    assert get_version(users.ana, v1)["backtest"] == backtest
    listed = users.ana.get(f"{API}/strategies/{strategy['id']}").json()
    assert listed["latest"]["pass_rate"] == summary["pass_rate"]

    # A candidate version against v1 on the labelled rows.
    v2 = users.ana.post(f"{API}/strategies/{strategy['id']}/versions", json={}).json()
    put(users.ana, v2, rule("R01", cond("income", "lt", 7500)), *V1_RULES[1:])
    body = {"dataset_id": dataset["id"], "compare_version_id": v1["id"]}
    compared = users.ana.post(f"{API}/strategy-versions/{v2['id']}/backtest", json=body).json()["backtest"]
    compare = compared["compare"]
    assert (compare["version_id"], compare["version"]) == (v1["id"], 1)
    assert compare["summary"] == summary
    assert compared["summary"]["reject"] > summary["reject"]
    cells = {(c["from"], c["to"]): c for c in compare["swap"]}
    assert len(cells) == 9 and sum(c["rows"] for c in cells.values()) == labelled.sum() == 210
    after = expected_decisions(frame, 7500)
    for (a, b), cell in cells.items():
        mask = labelled & (decisions == a) & (after == b)
        assert cell["rows"] == mask.sum(), (a, b)
        expected = frame.target[mask].mean() if mask.any() else None
        assert cell["bad_rate"] == (pytest.approx(expected, abs=1e-6) if mask.any() else None), (a, b)
    assert cells[("pass", "reject")]["rows"] > 0 and cells[("reject", "pass")]["rows"] == 0

    # Saving the rules discards the stale backtest.
    edited = put(users.ana, v2, *V1_RULES).json()
    assert edited["backtest"] == {} and edited["pass_rate"] is None

    # Without a target or a date there are no bad rates and no months.
    users.ana.patch(f"{API}/datasets/{dataset['id']}", json={"clear": ["target_column", "date_column"]})
    bare = users.ana.post(f"{API}/strategy-versions/{v2['id']}/backtest", json=body).json()["backtest"]
    assert "bad_rate" not in bare["summary"] and "monthly" not in bare["summary"]
    assert sum(c["rows"] for c in bare["compare"]["swap"]) == 240
    assert all(c["bad_rate"] is None for c in bare["compare"]["swap"])
    actions = db.scalars(
        select(AuditLog.action).where(AuditLog.action == "strategy_version.backtested")
    ).all()
    assert len(actions) == 3


def test_backtest_and_console_need_what_the_rules_reference(users):
    dataset = upload(users.ana, loan_csv(rows=60)).json()
    _, v1 = first_draft(users.ana)
    url = f"{API}/strategy-versions/{v1['id']}"
    empty = users.ana.post(f"{url}/backtest", json={"dataset_id": dataset["id"]}).json()
    assert empty["backtest"]["summary"]["pass_rate"] == 1 and empty["backtest"]["summary"]["rules"] == []

    put(users.ana, v1, rule("R01", cond("phone", "in_list", "BL_PHONE")))
    for response in (
        users.ana.post(f"{url}/backtest", json={"dataset_id": dataset["id"]}),
        console(users.ana, v1, {}),
    ):
        assert response.status_code == 400 and response.json()["code"] == "list_not_found"
        assert response.json()["detail"] == {"list": "BL_PHONE"}
    put(users.ana, v1, rule("R01", cond("model:RETAIL_APP.score", "lt", 500)))
    for response in (
        users.ana.post(f"{url}/backtest", json={"dataset_id": dataset["id"]}),
        console(users.ana, v1, {}),
    ):
        assert response.status_code == 400 and response.json()["code"] == "model_not_online"

    put(users.ana, v1, rule("R01", cond("income", "lt", 1)))
    assert (
        users.ana.post(f"{url}/backtest", json={"dataset_id": MISSING}).json()["code"] == "dataset_not_found"
    )
    body = {"dataset_id": dataset["id"], "compare_version_id": MISSING}
    assert users.ana.post(f"{url}/backtest", json=body).json()["code"] == "version_not_found"
    missing = f"{API}/strategy-versions/{MISSING}"
    assert users.ana.post(f"{missing}/backtest", json={"dataset_id": dataset["id"]}).status_code == 404
    assert console(users.ana, {"id": MISSING}, {}).json()["code"] == "version_not_found"


def test_the_console_explains_a_decision_without_logging_it(users, lists, db):
    _, v1 = first_draft(users.ana)
    put(users.ana, v1, *SIMPLE)
    response = console(users.bob, v1, {"phone": " 13800001234 ", "age": 19})
    assert response.status_code == 200, response.json()
    out = response.json()
    assert re.fullmatch(r"console-[0-9a-f]{12}", out["request_id"])
    assert (out["decision"], out["reason"], out["missing_fields"], out["scores"]) == (
        "reject",
        "BLACKLIST",
        ["income"],
        {},
    )
    assert out["rules"] == [
        {"code": "R01", "name": "rule R01", "name_en": None, "decision": "reject"},
        {"code": "R02", "name": "rule R02", "name_en": None, "decision": "reject"},
    ]
    assert out["strategy"] == {"code": CODE, "version": 1} and out["latency_ms"] >= 0
    assert [(t["code"], t["hit"]) for t in out["trace"]] == [
        ("W01", False),
        ("R01", True),
        ("R02", True),
        ("V01", False),
    ]
    phone = out["trace"][1]["when"]["items"][0]
    assert (phone["actual"], phone["value"], phone["result"]) == ("138****1234", "BL_PHONE", True)
    assert [i["actual"] for i in out["trace"][2]["when"]["items"]] == [19, 19]
    assert "13800001234" not in json.dumps(out)

    assert console(users.bob, v1, LOW).json()["reason"] == "V01"  # no reason: the rule code
    assert console(users.bob, v1, WHITE).json()["decision"] == "pass"
    nothing = console(users.bob, v1, {}).json()
    assert (nothing["decision"], nothing["reason"], nothing["rules"]) == ("pass", "", [])
    assert nothing["missing_fields"] == ["age", "income", "phone"]
    assert db.scalar(select(func.count()).select_from(DecisionLog)) == 0


# ---- Lifecycle ------------------------------------------------------------------------------------


def test_strategy_lifecycle(users, lists, db):
    strategy, v1 = first_draft(users.ana)
    put(users.ana, v1, *SIMPLE)
    for action in ("approve", "reject", "online", "retire"):
        response = act(users.root, v1, action)
        assert response.status_code == 409 and response.json()["code"] == "invalid_transition", action
        assert response.json()["detail"] == {"status": "draft"}
    assert act(users.root, v1, "publish").status_code == 404
    assert act(users.bob, v1, "submit").json()["code"] == "forbidden"

    submitted = act(users.ana, v1, "submit", " ready ").json()
    assert submitted["status"] == "in_review" and submitted["submitter"]["username"] == "ana"
    assert act(users.ana, v1, "approve").json()["code"] == "forbidden"
    rejected = act(users.root, v1, "reject", "tighten R02").json()
    assert (
        rejected["status"] == "draft" and rejected["submitter"] is None and rejected["submitted_at"] is None
    )
    assert act(users.ana, v1, "submit").status_code == 200
    approved = act(users.root, v1, "approve", "ok").json()
    assert approved["status"] == "approved" and approved["approver"]["username"] == "root"
    assert act(users.ana, v1, "online").json()["code"] == "forbidden"
    online = act(users.root, v1, "online").json()
    assert online["status"] == "online" and online["online_at"] is not None
    assert [(r["action"], r["actor"]["username"], r["comment"]) for r in online["reviews"]] == [
        ("submit", "ana", "ready"),
        ("reject", "root", "tighten R02"),
        ("submit", "ana", ""),
        ("approve", "root", "ok"),
        ("online", "root", ""),
    ]
    summary = users.bob.get(f"{API}/strategies").json()[0]
    assert summary["online"]["id"] == v1["id"] and summary["online"]["rule_count"] == 4

    retired = act(users.root, v1, "retire", "end").json()
    assert retired["status"] == "retired" and retired["retired_at"] is not None
    for action in ("submit", "approve", "online", "retire"):
        assert act(users.root, v1, action).status_code == 409, action
    assert users.bob.get(f"{API}/strategies/{strategy['id']}").json()["online"] is None
    actions = db.scalars(select(AuditLog.action).where(AuditLog.action.like("strategy_version.%"))).all()
    assert sorted(set(actions)) == [
        "strategy_version.approve",
        "strategy_version.online",
        "strategy_version.reject",
        "strategy_version.retire",
        "strategy_version.submit",
        "strategy_version.updated",
    ]


def test_four_eyes(users, lists, make_user, login, monkeypatch):
    strategy, v1 = first_draft(users.root)
    put(users.root, v1, *SIMPLE)
    assert act(users.root, v1, "submit").status_code == 200
    blocked = act(users.root, v1, "approve")
    assert blocked.status_code == 403 and blocked.json()["code"] == "four_eyes"
    assert act(users.rex, v1, "approve").json()["status"] == "approved"

    # Neither the author nor the administrator who submitted it may approve.
    v2 = users.root.post(f"{API}/strategies/{strategy['id']}/versions", json={}).json()
    assert act(users.rex, v2, "submit").status_code == 200
    assert act(users.root, v2, "approve").json()["code"] == "four_eyes"
    assert act(users.rex, v2, "approve").json()["code"] == "four_eyes"
    make_user("max", Role.admin)
    assert act(login("max"), v2, "approve").json()["status"] == "approved"

    v3 = users.root.post(f"{API}/strategies/{strategy['id']}/versions", json={}).json()
    act(users.root, v3, "submit")
    monkeypatch.setenv("KIVI_REQUIRE_FOUR_EYES", "false")
    get_settings.cache_clear()
    assert act(users.root, v3, "approve").json()["status"] == "approved"


def test_online_needs_rules_lists_and_online_models(users, db):
    strategy, v1 = first_draft(users.ana)
    # Role and state come first, before anything about the rules.
    assert act(users.ana, v1, "online").json()["code"] == "forbidden"
    assert act(users.root, v1, "online").json()["code"] == "invalid_transition"
    act(users.ana, v1, "submit")
    act(users.root, v1, "approve")
    empty = act(users.root, v1, "online")
    assert empty.status_code == 409 and empty.json()["code"] == "empty_strategy"

    rules = (SIMPLE[1], rule("M01", cond("model:RETAIL_APP.score", "lt", 500)))
    v2 = users.ana.post(
        f"{API}/strategies/{strategy['id']}/versions", json={"definition": definition(*rules)}
    ).json()
    act(users.ana, v2, "submit")
    act(users.root, v2, "approve")
    no_list = act(users.root, v2, "online")
    assert no_list.status_code == 409 and no_list.json()["code"] == "list_not_found"
    assert no_list.json()["detail"] == {"lists": ["BL_PHONE"]}
    new_list(users.ana)
    no_model = act(users.root, v2, "online")
    assert no_model.status_code == 409 and no_model.json()["code"] == "model_not_online"
    assert no_model.json()["detail"] == {"models": ["RETAIL_APP"]}
    users.ana.post(f"{API}/models", json={"code": "retail_app", "name": "评分卡"})  # no online version yet
    assert act(users.root, v2, "online").json()["code"] == "model_not_online"

    # Refusals leave the version as it was.
    v2 = get_version(users.ana, v2)
    assert v2["status"] == "approved" and v2["online_at"] is None
    assert [r["action"] for r in v2["reviews"]] == ["submit", "approve"]
    assert db.scalar(select(func.count()).where(AuditLog.action == "strategy_version.online")) == 0
    assert db.scalar(select(func.count()).where(StrategyVersion.status == "online")) == 0


def test_a_new_online_version_retires_the_previous_one(users, online, db):
    url = f"{API}/strategies/{online.strategy['id']}/versions"
    v2 = users.ana.post(url, json={}).json()
    assert to_online(users, v2)["status"] == "online"
    v1 = get_version(users.ana, online.version)
    assert v1["status"] == "retired" and v1["retired_at"] is not None
    last = v1["reviews"][-1]
    assert (last["action"], last["actor"]["username"], last["comment"]) == (
        "retire",
        "root",
        "replaced by v2",
    )
    assert users.ana.get(f"{API}/strategies/{online.strategy['id']}").json()["online"]["version"] == 2
    assert db.scalar(select(func.count()).where(StrategyVersion.status == "online")) == 1

    # A refused candidate leaves the online version in place.
    v3 = users.ana.post(url, json={}).json()
    put(users.ana, v3, *SIMPLE, rule("X01", cond("device", "in_list", "BL_DEVICE")))
    act(users.ana, v3, "submit")
    act(users.root, v3, "approve")
    assert act(users.root, v3, "online").json()["code"] == "list_not_found"
    v2 = get_version(users.ana, v2)
    assert v2["status"] == "online" and [r["action"] for r in v2["reviews"]][-1] == "online"
    assert get_version(users.ana, v3)["status"] == "approved"

    # An approved version can be retired without going online.
    assert act(users.root, v3, "retire").json()["status"] == "retired"
    assert users.ana.get(f"{API}/strategies/{online.strategy['id']}").json()["online"]["version"] == 2


def test_delete_rules(users, online, token, db):
    assert decide(token, GOOD).status_code == 200
    url = f"{API}/strategies/{online.strategy['id']}"
    assert users.bob.delete(url).json()["code"] == "forbidden"
    blocked = users.ana.delete(url)
    assert blocked.status_code == 409 and blocked.json()["code"] == "strategy_online"
    refused = users.ana.delete(f"{API}/strategy-versions/{online.version['id']}")
    assert refused.status_code == 409 and refused.json()["code"] == "invalid_transition"

    # Lists used by an online strategy stay; a draft referencing one does not hold it.
    _, other = first_draft(users.bob, "other")
    put(users.bob, other, rule("X", cond("phone", "in_list", "BL_PHONE")))
    black = users.ana.get(f"{API}/risk-lists").json()[0]
    in_use = users.ana.delete(f"{API}/risk-lists/{black['id']}")
    assert in_use.status_code == 409 and in_use.json()["code"] == "list_in_use"
    assert in_use.json()["detail"] == {"strategies": [CODE]}

    assert act(users.root, online.version, "retire").status_code == 200
    assert users.ana.delete(url).status_code == 204
    assert users.ana.get(url).json()["code"] == "strategy_not_found"
    assert users.ana.get(f"{API}/strategy-versions/{online.version['id']}").status_code == 404
    assert db.scalar(select(func.count()).select_from(Strategy)) == 1  # "OTHER"
    assert db.scalar(select(func.count()).select_from(StrategyVersion)) == 1
    assert db.scalar(select(func.count()).select_from(StrategyReview)) == 0
    [log] = db.scalars(select(DecisionLog)).all()  # the decision history stays
    assert (log.strategy_id, log.version_id, log.strategy_code) == (None, None, CODE)
    assert users.ana.delete(f"{API}/risk-lists/{black['id']}").status_code == 204
    assert decide(token, GOOD).json()["code"] == "strategy_not_online"


def test_strategies_require_sign_in(anon):
    strategy, version = f"{API}/strategies/{MISSING}", f"{API}/strategy-versions/{MISSING}"
    for response in (
        anon.get(f"{API}/strategies"),
        anon.post(f"{API}/strategies", json={"code": "S1", "name": "x"}),
        anon.get(f"{API}/strategies/fields"),
        anon.get(strategy),
        anon.patch(strategy, json={"name": "x"}),
        anon.delete(strategy),
        anon.post(f"{strategy}/versions", json={}),
        anon.get(version),
        anon.put(version, json={"definition": {}}),
        anon.delete(version),
        anon.post(f"{version}/backtest", json={"dataset_id": MISSING}),
        anon.post(f"{version}/evaluate", json={"data": {}}),
        anon.post(f"{version}/submit", json={}),
        anon.get(f"{API}/decisions"),
        anon.get(f"{API}/decisions/d-1"),
        anon.get(f"{API}/api-tokens"),
        anon.post(f"{API}/api-tokens", json={"name": "x"}),
        anon.delete(f"{API}/api-tokens/{MISSING}"),
    ):
        assert response.status_code == 401 and response.json()["code"] == "unauthenticated"


# ---- API tokens and the decision API --------------------------------------------------------------


def test_api_tokens(users, db):
    created = make_token(users.root, name=" gateway ", expires_days=30)
    plain = created["token"]
    assert plain.startswith("kv_") and len(plain) > 40 and created["prefix"] == plain[:10]
    assert (created["name"], created["owner"]["username"]) == ("gateway", "root")
    assert created["revoked_at"] is None and created["last_used_at"] is None
    expires = datetime.fromisoformat(created["expires_at"])
    assert abs(expires - (datetime.now(UTC) + timedelta(days=30))) < timedelta(minutes=1)
    forever = make_token(users.root, name="batch")
    assert forever["expires_at"] is None and forever["token"] != plain

    listed = users.root.get(f"{API}/api-tokens").json()
    assert [t["name"] for t in listed] == ["batch", "gateway"] and all("token" not in t for t in listed)
    row = db.scalar(select(ApiToken).where(ApiToken.name == "gateway"))
    assert row.token_hash == hashlib.sha256(plain.encode()).hexdigest()
    stored = json.dumps(
        [[str(getattr(t, c.key)) for c in ApiToken.__table__.columns] for t in db.scalars(select(ApiToken))]
    )
    stored += json.dumps([a.detail for a in db.scalars(select(AuditLog)).all()])
    assert plain not in stored and forever["token"] not in stored

    for response in (
        users.ana.get(f"{API}/api-tokens"),
        users.ana.post(f"{API}/api-tokens", json={"name": "mine"}),
        users.ana.delete(f"{API}/api-tokens/{created['id']}"),
    ):
        assert response.status_code == 403 and response.json()["code"] == "forbidden"
    assert users.root.post(f"{API}/api-tokens", json={"name": "x", "expires_days": 0}).status_code == 422
    assert users.root.post(f"{API}/api-tokens", json={"name": ""}).status_code == 422

    revoked = users.root.delete(f"{API}/api-tokens/{created['id']}").json()
    assert revoked["revoked_at"] is not None
    assert users.rex.delete(f"{API}/api-tokens/{created['id']}").json()["revoked_at"] == revoked["revoked_at"]
    assert users.root.delete(f"{API}/api-tokens/{MISSING}").json()["code"] == "token_not_found"
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_type == "token")).all()
    assert sorted(actions) == ["token.created", "token.created", "token.revoked"]


def test_decide_needs_a_valid_bearer_token(users, online, db):
    good = make_token(users.root)["token"]
    revoked = make_token(users.root, name="old")
    users.root.delete(f"{API}/api-tokens/{revoked['id']}")
    expired = make_token(users.root, name="expired", expires_days=1)
    db.execute(
        update(ApiToken)
        .where(ApiToken.id == uuid.UUID(expired["id"]))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()

    bare = machine()
    for headers, code in (
        ({}, "token_required"),
        ({"Authorization": f"Basic {good}"}, "token_required"),
        ({"Authorization": good}, "token_required"),
        ({"Authorization": "Bearer kv_wrong"}, "invalid_token"),
        ({"Authorization": f"Bearer {revoked['token']}"}, "invalid_token"),
        ({"Authorization": f"Bearer {expired['token']}"}, "invalid_token"),
    ):
        response = bare.post(f"{API}/decide/{CODE}", json={"data": GOOD}, headers=headers)
        assert response.status_code == 401 and response.json()["code"] == code, headers
    # Tokens are checked before anything about the strategy, and a session is no substitute.
    assert decide("kv_wrong", GOOD, code="NOPE").json()["code"] == "invalid_token"
    assert users.ana.post(f"{API}/decide/{CODE}", json={"data": GOOD}).json()["code"] == "token_required"

    # No X-Requested-With header is needed here, unlike for cookie sessions.
    response = decide(good, GOOD, client=bare)
    assert response.status_code == 200, response.json()
    assert (
        bare.post(f"{API}/risk-lists", json={"code": "X1", "name": "x"}).json()["code"]
        == "csrf_header_missing"
    )
    assert decide(f"  {good}  ", GOOD).status_code == 200
    used = db.scalar(
        select(ApiToken.last_used_at).where(ApiToken.token_hash == hashlib.sha256(good.encode()).hexdigest())
    )
    assert used is not None and datetime.now(UTC) - used < timedelta(minutes=1)
    assert db.scalar(select(func.count()).select_from(DecisionLog)) == 2


def test_decide_logs_masked_input_and_replays_request_ids(users, online, token, db):
    data = BLACK | {"extra": {"nested": [1, 2]}, "flag": True, "note": None}
    response = decide(token, data, request_id="req-001")
    assert response.status_code == 200, response.json()
    first = response.json()
    assert first == {
        "request_id": "req-001",
        "decision": "reject",
        "reason": "BLACKLIST",
        "rules": [{"code": "R01", "name": "rule R01", "name_en": None, "decision": "reject"}],
        "scores": {},
        "strategy": {"code": CODE, "version": 1},
        "missing_fields": [],
        "latency_ms": first["latency_ms"],
        "replayed": False,
    }
    assert first["latency_ms"] >= 0
    log = db.scalar(select(DecisionLog).where(DecisionLog.request_id == "req-001"))
    assert log.input == {
        "phone": "138****1234",
        "age": 30,
        "income": 9000,
        "extra": "{'nested': [1, 2]}",
        "flag": True,
        "note": None,
    }
    assert (log.decision, log.reason, log.hit_rules, log.source, log.version) == (
        "reject",
        "BLACKLIST",
        ["R01"],
        "api",
        1,
    )
    assert log.strategy_id is not None and str(log.version_id) == online.version["id"]
    assert log.token_id == db.scalar(select(ApiToken.id))
    assert [t["code"] for t in log.trace] == ["W01", "R01", "R02", "V01"]
    assert "13800001234" not in json.dumps([log.input, log.trace])

    # The same request id answers from the log, whatever the new data says.
    again = decide(token, GOOD, request_id="req-001").json()
    assert again["replayed"] is True
    assert {k: again[k] for k in ("request_id", "decision", "reason", "rules", "strategy")} == {
        k: first[k] for k in ("request_id", "decision", "reason", "rules", "strategy")
    }
    assert db.scalar(select(func.count()).select_from(DecisionLog)) == 1

    fresh = decide(token, WHITE, code="retail_apply").json()
    assert re.fullmatch(r"d-[0-9a-f]{20}", fresh["request_id"]) and fresh["strategy"]["code"] == CODE
    assert (fresh["decision"], fresh["reason"]) == ("pass", "WHITELIST")
    assert [r["code"] for r in fresh["rules"]] == ["W01", "R01"]  # every hit is reported
    assert decide(token, {}).json()["missing_fields"] == ["age", "income", "phone"]
    assert decide(token, GOOD, request_id="has space").status_code == 422

    for code in ("NOPE", "other"):
        missing = decide(token, GOOD, code=code)
        assert missing.status_code == 404 and missing.json()["code"] == "strategy_not_online"
    first_draft(users.ana, "other")  # a strategy with only a draft is not online either
    assert decide(token, GOOD, code="other").json()["code"] == "strategy_not_online"


def test_decide_matches_the_console(users, retail_model, lists, token, db):
    result = retail_model.version["result"]
    cut = int(result["score_stats"]["mean"])
    strategy, v1 = first_draft(users.ana)
    rules = (
        *SIMPLE[:2],
        rule("R02", cond("年龄", "lt", 23)),
        rule("S01", cond("model:RETAIL_APP.score", "lt", cut), decision="review", reason="LOW_SCORE"),
        rule("S02", cond("model:RETAIL_APP.prob", "gt", 0.5), cond("city", "is_null")),
    )
    put(users.ana, v1, *rules)
    v1 = to_online(users, v1)
    records = json.loads(loan_frame(rows=240, seed=11).head(16).to_json(orient="records"))
    for i, record in enumerate(records):
        record["phone"] = ["13800001234", "13800005678", "13700000000", None][i % 4]
    records.append({"phone": "13700000000"})  # every model input missing
    decisions, scores = set(), set()
    for record in records:
        expected = console(users.bob, v1, record).json()
        got = decide(token, record).json()
        for key in ("decision", "reason", "rules", "scores", "missing_fields", "strategy"):
            assert got[key] == expected[key], (key, record)
        assert set(got["scores"]) == {"RETAIL_APP"}
        assert isinstance(got["scores"]["RETAIL_APP"]["score"], int)
        assert 0 < got["scores"]["RETAIL_APP"]["probability"] < 1
        decisions.add(got["decision"])
        scores.add(got["scores"]["RETAIL_APP"]["score"])
    assert decisions == {"pass", "review", "reject"} and len(scores) > 3
    # Missing rule fields and missing model inputs are both reported.
    lacking = set(decide(token, records[-1]).json()["missing_fields"])
    assert lacking >= {"年龄", "city"} | {f["code"] for f in result["features"]}

    # An online strategy keeps its model online: retiring the model is refused.
    refused = users.root.post(
        f"{API}/model-versions/{retail_model.version['id']}/retire", json={"comment": ""}
    )
    assert refused.status_code == 409 and refused.json()["code"] == "model_in_use"
    assert refused.json()["detail"] == {"strategies": [CODE]}
    assert decide(token, records[0]).status_code == 200

    # If the model goes offline anyway (here behind the API's back), decisions fail loudly.
    db.execute(
        update(ModelVersion)
        .where(ModelVersion.id == uuid.UUID(retail_model.version["id"]))
        .values(status="retired")
    )
    db.commit()
    runtime.invalidate(CODE)
    broken = decide(token, records[0])
    assert broken.status_code == 422 and broken.json()["code"] == "model_not_online"
    assert broken.json()["detail"] == {"model": "RETAIL_APP"}


def test_lifecycle_changes_reach_the_decision_api_at_once(users, online, token, db):
    assert decide(token, GOOD).json()["decision"] == "pass"
    v2 = users.ana.post(f"{API}/strategies/{online.strategy['id']}/versions", json={}).json()
    put(users.ana, v2, *SIMPLE, rule("R09", cond("income", "lt", 10000)))
    assert decide(token, GOOD).json()["decision"] == "pass"  # a draft changes nothing
    to_online(users, v2)
    taken = decide(token, GOOD).json()
    assert (taken["decision"], taken["strategy"]["version"], taken["reason"]) == ("reject", 2, "R09")

    # The online version is cached for a short time: edits behind the API's back wait for it.
    db.execute(
        update(StrategyVersion)
        .where(StrategyVersion.id == uuid.UUID(v2["id"]))
        .values(definition=definition(*SIMPLE))
    )
    db.commit()
    assert decide(token, GOOD).json()["decision"] == "reject"
    runtime.invalidate(CODE)
    assert decide(token, GOOD).json()["decision"] == "pass"

    act(users.root, v2, "retire")
    assert decide(token, GOOD).json()["code"] == "strategy_not_online"


def test_watchlist_changes_reach_the_decision_api_at_once(users, online, lists, token):
    assert decide(token, GOOD).json()["decision"] == "pass"
    assert add_items(users.bob, lists.black, GOOD["phone"]).json()["added"] == 1
    assert (decide(token, GOOD).json()["reason"]) == "BLACKLIST"
    items = users.bob.get(f"{API}/risk-lists/{lists.black['id']}/items", params={"q": GOOD["phone"]}).json()
    assert items["total"] == 1
    gone = users.bob.delete(f"{API}/risk-lists/{lists.black['id']}/items/{items['items'][0]['id']}")
    assert gone.status_code == 204
    assert decide(token, GOOD).json()["decision"] == "pass"


def test_a_model_used_by_an_online_strategy_stays_online(users, retail_model, lists):
    model_url = f"{API}/model-versions/{retail_model.version['id']}"
    strategy, v1 = first_draft(users.ana)
    put(users.ana, v1, rule("S01", cond("model:retail_app.score", "lt", 500)))
    stored = get_version(users.ana, v1)["definition"]["rules"][0]["when"]["items"][0]
    assert stored["field"] == "model:RETAIL_APP.score"  # model codes are upper-cased
    v1 = to_online(users, v1)
    refused = users.root.post(f"{model_url}/retire", json={"comment": ""})
    assert refused.status_code == 409 and refused.json()["code"] == "model_in_use"
    assert users.root.get(model_url).json()["status"] == "online"
    # Once the strategy is retired the model can go.
    assert act(users.root, v1, "retire").status_code == 200
    assert users.root.post(f"{model_url}/retire", json={"comment": ""}).json()["status"] == "retired"


def test_request_ids_belong_to_one_strategy(users, online, token, db, monkeypatch):
    other, draft = first_draft(users.ana, "other_apply")
    put(users.ana, draft, rule("R01", cond("age", "lt", 18)))
    to_online(users, draft)
    assert decide(token, GOOD, request_id="shared-1").json()["replayed"] is False
    clash = decide(token, GOOD, code="other_apply", request_id="shared-1")
    assert clash.status_code == 409 and clash.json()["code"] == "request_id_conflict"
    assert clash.json()["detail"] == {"strategy": CODE}

    # A concurrent duplicate loses the insert race and answers as a replay, not a 500.
    from kivi_ui.routes import decisions

    real, calls = decisions._previous, []

    def racing(db_, request_id, code):
        calls.append(request_id)
        return None if len(calls) == 1 else real(db_, request_id, code)

    monkeypatch.setattr(decisions, "_previous", racing)
    raced = decide(token, BLACK, request_id="shared-1")
    assert raced.status_code == 200 and raced.json()["replayed"] is True
    assert raced.json()["decision"] == "pass" and calls == ["shared-1", "shared-1"]
    assert db.scalar(select(func.count()).where(DecisionLog.request_id == "shared-1")) == 1


def test_watchlist_fields_are_masked_in_stored_traces(users, lists, token, db):
    strategy, v1 = first_draft(users.ana)
    put(
        users.ana,
        v1,
        rule("R01", cond("phone", "in_list", "bl_phone")),  # list codes are upper-cased
        rule("R02", cond("phone", "eq", "13700000000"), decision="review"),
    )
    assert get_version(users.ana, v1)["definition"]["rules"][0]["when"]["items"][0]["value"] == "BL_PHONE"
    to_online(users, v1)
    out = decide(token, GOOD, request_id="mask-1").json()
    assert (out["decision"], [r["code"] for r in out["rules"]]) == ("review", ["R02"])
    log = db.scalar(select(DecisionLog).where(DecisionLog.request_id == "mask-1"))
    leaves = [rule["when"]["items"][0] for rule in log.trace]
    assert [leaf["actual"] for leaf in leaves] == ["137****0000", "137****0000"]
    assert "13700000000" not in json.dumps([log.input, [leaf["actual"] for leaf in leaves]])


def make_decisions(token) -> list[str]:
    ids = []
    for request_id, data in (
        ("a-1", BLACK),
        ("a-2", YOUNG),
        ("a-3", LOW),
        ("b-1", GOOD),
        ("b-2", WHITE),
        ("b-3", {"age": 40}),
    ):
        response = decide(token, data, request_id=request_id)
        assert response.status_code == 200, response.json()
        ids.append(request_id)
    return ids


def test_the_decision_log(users, online, token, db):
    make_decisions(token)
    db.execute(
        update(DecisionLog)
        .where(DecisionLog.request_id == "a-1")
        .values(created_at=datetime.now(UTC) - timedelta(days=3))
    )
    db.commit()

    def page(**params) -> dict:
        response = users.bob.get(f"{API}/decisions", params=params)
        assert response.status_code == 200, response.json()
        return response.json()

    def ids(**params) -> list[str]:
        return [i["request_id"] for i in page(**params)["items"]]

    everything = page()
    assert everything["total"] == 6 and everything["counts"] == {"pass": 3, "review": 1, "reject": 2}
    assert ids() == ["b-3", "b-2", "b-1", "a-3", "a-2", "a-1"]  # newest first
    item = everything["items"][-1]
    assert (item["strategy_code"], item["version"], item["decision"], item["reason"], item["source"]) == (
        CODE,
        1,
        "reject",
        "BLACKLIST",
        "api",
    )
    assert (
        item["hit_rules"] == ["R01"] and item["scores"] == {} and "trace" not in item and "input" not in item
    )

    # The decision filter narrows the page; the counts show the split it was taken from.
    rejected = page(decision="reject")
    assert [i["request_id"] for i in rejected["items"]] == ["a-2", "a-1"] and rejected["total"] == 2
    assert rejected["counts"] == {"pass": 3, "review": 1, "reject": 2}
    assert ids(rule="R01") == ["b-2", "a-1"]
    assert page(rule="V01")["counts"] == {"pass": 0, "review": 1, "reject": 1}
    assert ids(q="a-") == ["a-3", "a-2", "a-1"] and ids(q="a-", decision="pass") == []
    assert ids(q="b-", decision="pass") == ["b-3", "b-2", "b-1"]
    assert page(strategy="retail_apply")["total"] == 6
    none = page(strategy="OTHER")
    assert none["total"] == 0 and none["counts"] == {"pass": 0, "review": 0, "reject": 0}
    assert page(source="api")["total"] == 6 and page(source="demo")["total"] == 0
    cut = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert ids(since=cut) == ["b-3", "b-2", "b-1", "a-3", "a-2"] and ids(until=cut) == ["a-1"]
    assert ids(size=2, page=2) == ["b-1", "a-3"] and page(size=2)["total"] == 6
    assert users.bob.get(f"{API}/decisions", params={"decision": "maybe"}).status_code == 422

    detail = users.bob.get(f"{API}/decisions/a-1").json()
    assert detail["input"] == {"phone": "138****1234", "age": 30, "income": 9000}
    assert [(t["code"], t["hit"]) for t in detail["trace"]] == [
        ("W01", False),
        ("R01", True),
        ("R02", False),
        ("V01", False),
    ]
    assert detail["trace"][1]["when"]["items"][0]["actual"] == "138****1234"
    missing = users.bob.get(f"{API}/decisions/nope")
    assert missing.status_code == 404 and missing.json()["code"] == "decision_not_found"


# ---- Demo content ---------------------------------------------------------------------------------


def test_seed_strategy_is_idempotent_and_refresh_removes_it(make_user, db, login):
    admin, analyst = make_user("root", Role.admin), make_user("analyst")
    assert seed_strategy(db, admin, analyst) == []  # nothing to build on yet

    def seed() -> list[str]:
        seed_datasets(db, admin, as_of=date(2026, 11, 19))
        seed_model(db, admin, analyst)
        return seed_strategy(db, admin, analyst)

    created = seed()
    logs = db.scalar(select(func.count()).select_from(DecisionLog))
    assert created == [
        f"watchlist {BLACKLIST} (90)",
        f"watchlist {WHITELIST} (25)",
        f"strategy {STRATEGY_CODE} v1 online, v2 draft",
        f"{logs} demo decisions",
    ]
    assert logs > 100
    strategy = db.scalar(select(Strategy))
    v2, v1 = strategy.versions
    assert (v1.status, v2.status, strategy.owner_id) == ("online", "draft", analyst.id)
    assert (len(v1.definition["rules"]), len(v2.definition["rules"])) == (8, 9)
    assert sorted(r.action for r in v1.reviews) == ["approve", "online", "submit"] and v2.reviews == []
    retail = db.scalar(select(Dataset).where(Dataset.name == RETAIL))
    assert v1.backtest["summary"]["rows"] == v2.backtest["summary"]["rows"] == retail.row_count
    assert sum(c["rows"] for c in v2.backtest["compare"]["swap"]) == retail.row_count
    assert v2.backtest["compare"]["summary"] == v1.backtest["summary"]
    assert {r["code"]: r["hits"] for r in v1.backtest["summary"]["rules"]}["R01"] > 0
    counts = dict(
        db.execute(
            select(RiskList.code, func.count())
            .join(RiskListItem, RiskListItem.list_id == RiskList.id)
            .group_by(RiskList.code)
        ).all()
    )
    assert counts == {BLACKLIST: 90, WHITELIST: 25}
    stored = db.scalars(select(DecisionLog)).all()
    assert {(d.source, d.strategy_code, d.version) for d in stored} == {("demo", STRATEGY_CODE, 1)}
    assert all(re.fullmatch(r"1\d\d\*{4}\d{4}", d.input["phone"]) for d in stored), stored[0].input["phone"]

    # The decision API reaches the same decisions as the backtest that produced the history.
    root = login("root")
    token = make_token(root)["token"]
    frame = store.read_columns(db, retail, [c.column_name for c in retail.columns])
    by_id = {f"demo-{a}": i for i, a in enumerate(frame.application_id)}
    for log in sorted(stored, key=lambda d: d.request_id)[:12]:
        record = json.loads(frame.iloc[[by_id[log.request_id]]].to_json(orient="records", date_format="iso"))[
            0
        ]
        record["phone"] = normalise_value(record["phone"])  # callers send the number as text
        got = decide(token, record).json()
        assert (got["decision"], [r["code"] for r in got["rules"]]) == (log.decision, log.hit_rules), (
            log.request_id
        )
        assert got["scores"] == log.scores
    assert login("analyst").get(f"{API}/decisions", params={"source": "demo"}).json()["total"] == logs

    assert seed_strategy(db, admin, analyst) == []
    assert db.scalar(select(func.count()).select_from(StrategyVersion)) == 2
    assert db.scalar(select(func.count()).select_from(DecisionLog)) == logs + 12

    refresh(db)
    runtime.invalidate()
    for cls in (Strategy, StrategyVersion, RiskList, RiskListItem, DecisionLog, RiskModel, Dataset):
        assert db.scalar(select(func.count()).select_from(cls)) == 0, cls.__name__
    assert seed()[:3] == created[:3]
    assert db.scalar(select(func.count()).select_from(DecisionLog)) == logs
