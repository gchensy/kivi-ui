import re
from datetime import date

import pandas as pd
import pytest
from conftest import loan_frame, upload
from sqlalchemy import func, select, text

from kivi_ui.data import store
from kivi_ui.demo import BANK, RETAIL, seed_datasets
from kivi_ui.models import AuditLog, BinningScheme, Dataset, DatasetColumn, Indicator, Role

FEATURES = {"income", "city", "outcome", "responded", "c8"}


def data_tables(db) -> set[str]:
    rows = db.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
        {"s": store.SCHEMA},
    )
    return set(rows.scalars())


def by_column(body: dict) -> dict[str, dict]:
    return {c["column_name"]: c for c in body["columns"]}


# ---- Store: reading, naming, types and roles ------------------------------------------------


def test_gbk_and_other_delimiters_parse():
    csv_text = "编号,年龄,城市\n" + "".join(f"{i},{20 + i},{'北京' if i % 2 else '上海'}\n" for i in range(5))
    frame = store.read_csv(csv_text.encode("gbk"))
    assert frame.columns.tolist() == ["编号", "年龄", "城市"]
    assert frame["城市"].tolist()[:2] == ["上海", "北京"] and frame["年龄"].sum() == 110

    for delimiter in (";", "\t", "|"):
        content = "\n".join([delimiter.join("abc"), *[delimiter.join(["1", "2.5", "x"])] * 3])
        frame = store.read_csv(content.encode())
        assert frame.columns.tolist() == ["a", "b", "c"] and frame.shape == (3, 3)
        assert frame["b"].sum() == pytest.approx(7.5)
    assert store.read_csv(b"\xef\xbb\xbfid,x\n1,2\n").columns.tolist() == ["id", "x"]  # BOM dropped


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "empty_file"),
        (b"  \n\n", "empty_file"),
        (b"a,b\n", "empty_file"),
        (b"\xff\xfe\xff", "bad_encoding"),
        (b"only\n1\n2\n", "too_few_columns"),
        (b"a,b\n1,2\n3,4,5,6\n", "bad_csv"),
    ],
)
def test_unreadable_files(content, code):
    with pytest.raises(store.DataError) as error:
        store.read_csv(content)
    assert error.value.code == code


def test_read_limits(monkeypatch):
    content = b"a,b,c\n" + b"1,2,3\n" * 10
    monkeypatch.setattr(store, "MAX_ROWS", 9)
    with pytest.raises(store.DataError, match="Too many rows"):
        store.read_csv(content)
    monkeypatch.setattr(store, "MAX_COLUMNS", 2)
    with pytest.raises(store.DataError, match="Too many columns"):
        store.read_csv(content)
    monkeypatch.setattr(store, "MAX_BYTES", len(content) - 1)
    with pytest.raises(store.DataError, match="larger than"):
        store.read_csv(content)


def test_sanitize_makes_unique_sql_names():
    headers = ["Age", "age", "AGE", "1st loan", "月收入", "收入 (元)", "", "Apply Date", "a" * 80, "age_2"]
    names = store.sanitize(headers)
    assert names[:8] == ["age", "age_2", "age_3", "c4_1st_loan", "c5", "c6", "c7", "apply_date"]
    assert len(set(names)) == len(names)
    assert all(re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", n) for n in names)
    assert all(store._quote(n) == f'"{n}"' for n in names)


def test_infer_dtype():
    months = pd.Series(["jan", "feb", "mar", "apr", "may", "jun"] * 5)
    assert store.infer_dtype(months, "month") == "category"
    assert store.infer_dtype(pd.Series(["2026-01", "2026-02"] * 10), "month") == "datetime"
    assert store.infer_dtype(pd.Series(["2026/01/03", "2026/02/04"] * 10), "applied") == "datetime"
    assert store.infer_dtype(pd.Series(["1.5", "2", "3"] * 40 + ["n/a"]), "amount") == "numeric"
    assert store.infer_dtype(pd.Series([True, False] * 5), "flag") == "category"
    assert store.infer_dtype(pd.Series([f"note {i}" for i in range(100)]), "remark") == "text"
    assert store.infer_dtype(pd.Series([None, None], dtype=object), "empty") == "text"


def test_guess_roles():
    rows = 30
    frame = pd.DataFrame(
        {
            "user_id": range(rows),
            "amount": [i * 1.5 for i in range(rows)],
            "default": [0, 1] * 15,
            "target": [1, 0, 0] * 10,
            "applied": ["2026-01-01"] * rows,
        }
    )
    data, meta = store.normalise(frame)
    assert store.guess_roles(data, meta) == {
        "target_column": "target",
        "target_event": None,
        "date_column": "applied",
        "id_column": "user_id",
    }
    # A target that is not binary is skipped for the next candidate; yes/no labels get an event.
    frame["target"] = [0, 1, 2] * 10
    frame["default"] = ["yes", "no"] * 15
    data, meta = store.normalise(frame)
    roles = store.guess_roles(data, meta)
    assert (roles["target_column"], roles["target_event"]) == ("default", "yes")
    # Unique numbers are an id only when the name says so.
    data, meta = store.normalise(frame.rename(columns={"user_id": "score"}))
    assert store.guess_roles(data, meta)["id_column"] is None


def test_validate_target():
    def check(values, event=None):
        return store.validate_target(pd.DataFrame({"t": values}), "t", event)

    with pytest.raises(store.DataError) as error:
        check(["a", "b", "c", "a"])
    assert error.value.code == "target_not_binary" and error.value.detail["values"] == ["a", "b", "c"]
    assert check([0, 1, None, 1]) is None
    assert check(["yes", "no", "no"]) == "yes"  # guessed
    assert check(["yes", "no", "no"], "no") == "no"
    with pytest.raises(store.DataError) as error:
        check(["paid", "overdue", "paid"])
    assert error.value.code == "target_event_required"
    assert error.value.detail["values"] == ["overdue", "paid"]
    assert check(["paid", "overdue"], "overdue") == "overdue"
    with pytest.raises(store.DataError, match="bad outcome"):
        check(["paid", "overdue"], "late")


def test_labels_use_the_event_and_keep_missing():
    frame = pd.DataFrame({"t": ["paid", "overdue", None, "paid"]})
    labels = store.labels(Dataset(target_column="t", target_event="overdue"), frame)
    assert labels.tolist()[:2] == [0.0, 1.0] and pd.isna(labels[2]) and labels[3] == 0


# ---- API ------------------------------------------------------------------------------------


def test_upload_detects_roles_and_profiles(make_user, login, db):
    make_user("ana")
    ana = login("ana")
    response = upload(ana, name="  ")
    assert response.status_code == 201, response.json()
    body = response.json()
    frame = loan_frame()

    assert body["name"] == "loans" and body["file_name"] == "loans.csv" and body["source"] == "upload"
    assert body["owner"]["username"] == "ana" and body["indicator_count"] == 0
    assert (body["row_count"], body["column_count"]) == (240, 8)
    assert (body["target_column"], body["target_event"]) == ("target", None)
    assert (body["date_column"], body["id_column"]) == ("apply_date", "id")
    assert body["bad_rate"] == pytest.approx(frame.target.mean())

    columns = by_column(body)
    assert [c["position"] for c in body["columns"]] == list(range(8))
    assert {name: c["role"] for name, c in columns.items()} == {
        "id": "id",
        "apply_date": "date",
        "income": "feature",
        "city": "feature",
        "target": "target",
        "outcome": "feature",
        "responded": "feature",
        "c8": "feature",
    }
    assert columns["c8"]["name"] == "年龄"
    assert {name: c["dtype"] for name, c in columns.items() if c["dtype"] != "category"} == {
        "id": "numeric",
        "apply_date": "datetime",
        "income": "numeric",
        "target": "numeric",
        "c8": "numeric",
    }
    income, city = columns["income"], columns["city"]
    assert income["missing_rate"] == pytest.approx(frame.income.isna().mean())
    assert income["stats"]["min"] == frame.income.min() and income["stats"]["p50"] == frame.income.median()
    assert city["missing_rate"] == pytest.approx(frame.city.isna().mean()) and city["unique_count"] == 3
    assert {t["value"] for t in city["stats"]["top"]} == {"east", "north", "south"}
    assert columns["apply_date"]["stats"]["min"].startswith("2026-01-")
    assert all(columns[name]["iv"] > 0 for name in FEATURES)
    assert all(columns[name]["iv"] is None for name in ("id", "apply_date", "target"))

    monthly = body["profile"]["monthly"]
    assert [m["month"] for m in monthly] == [f"2026-{m:02d}" for m in range(1, 7)]
    assert sum(m["rows"] for m in monthly) == 240
    assert sum(m["bad_rate"] * m["rows"] for m in monthly) == pytest.approx(frame.target.sum())

    assert data_tables(db) == {db.get(Dataset, body["id"]).table_name}
    listed = ana.get("/api/v1/datasets").json()
    assert [d["id"] for d in listed] == [body["id"]] and "columns" not in listed[0]
    assert ana.get(f"/api/v1/datasets/{body['id']}").json() == body


def test_preview_pages_through_rows(make_user, login):
    make_user("ana")
    ana = login("ana")
    dataset = upload(ana).json()
    url = f"/api/v1/datasets/{dataset['id']}/preview"

    frame = loan_frame()
    first = ana.get(url, params={"limit": 100}).json()
    assert first["columns"] == list(frame.columns)  # original headers
    assert first["total"] == 240 and len(first["rows"]) == 100
    rest = ana.get(url, params={"limit": 200, "offset": 100}).json()["rows"]
    assert len(rest) == 140
    assert sorted(row[0] for row in first["rows"] + rest) == list(range(1, 241))
    assert ana.get(url, params={"offset": 240}).json()["rows"] == []

    row = next(r for r in first["rows"] + rest if r[0] == 1)
    assert row[1] == f"{frame.apply_date[0]}T00:00:00" and row[3:] == list(frame.iloc[0, 3:])
    assert row[2] is None and frame.income.isna()[0]  # missing values come back as null
    assert ana.get(url, params={"limit": 500}).json()["code"] == "validation_error"


def test_patch_target_to_text_labels(make_user, login):
    make_user("ana")
    ana = login("ana")
    dataset = upload(ana).json()
    url = f"/api/v1/datasets/{dataset['id']}"
    frame = loan_frame()

    needs_event = ana.patch(url, json={"target_column": "outcome"})
    assert needs_event.status_code == 400
    assert needs_event.json()["code"] == "target_event_required"
    assert needs_event.json()["detail"]["values"] == ["overdue", "paid"]

    body = ana.patch(url, json={"target_column": "outcome", "target_event": "overdue"}).json()
    assert (body["target_column"], body["target_event"]) == ("outcome", "overdue")
    assert body["bad_rate"] == pytest.approx((frame.outcome == "overdue").mean())
    assert body["bad_rate"] != pytest.approx(dataset["bad_rate"])
    columns = by_column(body)
    assert columns["outcome"]["role"] == "target" and columns["outcome"]["iv"] is None
    assert columns["target"]["role"] == "feature" and columns["target"]["iv"] is not None
    assert columns["income"]["iv"] != by_column(dataset)["income"]["iv"]  # re-profiled
    january = body["profile"]["monthly"][0]
    assert january["bad_rate"] == pytest.approx((frame.outcome[:40] == "overdue").mean())

    guessed = ana.patch(url, json={"target_column": "responded"}).json()
    assert guessed["target_event"] == "yes"
    assert guessed["bad_rate"] == pytest.approx((frame.responded == "yes").mean())
    assert by_column(guessed)["outcome"]["role"] == "feature"
    chosen = ana.patch(url, json={"target_column": "responded", "target_event": "no"}).json()
    assert chosen["target_event"] == "no"
    assert chosen["bad_rate"] == pytest.approx((frame.responded == "no").mean())

    three = ana.patch(url, json={"target_column": "city"})
    assert three.status_code == 400 and three.json()["code"] == "target_not_binary"
    assert ana.patch(url, json={"target_column": "nope"}).json()["code"] == "unknown_column"
    assert ana.patch(url, json={"target_column": "responded", "target_event": "maybe"}).status_code == 400


def test_patch_roles_names_and_clearing(make_user, login):
    make_user("ana")
    ana = login("ana")
    dataset = upload(ana).json()
    url = f"/api/v1/datasets/{dataset['id']}"

    assert ana.patch(url, json={"date_column": "income"}).json()["code"] == "not_a_date"
    assert ana.patch(url, json={"roles": {"target": "feature"}}).json()["code"] == "invalid_role"
    assert ana.patch(url, json={"roles": {"income": "target"}}).json()["code"] == "invalid_role"
    assert ana.patch(url, json={"roles": {"income": "boss"}}).status_code == 422

    body = ana.patch(
        url, json={"roles": {"income": "ignore"}, "name": " Loans ", "description": " d "}
    ).json()
    assert (body["name"], body["description"]) == ("Loans", "d")
    assert by_column(body)["income"]["role"] == "ignore" and by_column(body)["income"]["iv"] is None

    cleared = ana.patch(url, json={"clear": ["target_column", "date_column"]}).json()
    assert cleared["target_column"] is cleared["target_event"] is cleared["bad_rate"] is None
    assert cleared["date_column"] is None and cleared["profile"]["monthly"] == []
    columns = by_column(cleared)
    assert (columns["target"]["role"], columns["apply_date"]["role"]) == ("feature", "ignore")
    assert all(c["iv"] is None for c in cleared["columns"])
    no_target = ana.post(f"{url}/screening", json={})
    assert no_target.status_code == 400 and no_target.json()["code"] == "no_target"

    restored = ana.patch(url, json={"target_column": "target", "date_column": "apply_date"}).json()
    assert restored["bad_rate"] == pytest.approx(dataset["bad_rate"])
    assert len(restored["profile"]["monthly"]) == 6


def test_only_owner_or_admin_change_datasets(make_user, login, db):
    make_user("ana")
    make_user("bob")
    make_user("root", Role.admin)
    ana, bob, admin = login("ana"), login("bob"), login("root")
    first, second = upload(ana).json(), upload(ana, name="second").json()

    assert bob.get(f"/api/v1/datasets/{first['id']}").status_code == 200
    denied = bob.patch(f"/api/v1/datasets/{first['id']}", json={"name": "mine"})
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden"
    assert bob.delete(f"/api/v1/datasets/{first['id']}").status_code == 403
    renamed = admin.patch(f"/api/v1/datasets/{first['id']}", json={"name": "renamed"})
    assert renamed.json()["name"] == "renamed"

    assert data_tables(db) == {db.get(Dataset, d["id"]).table_name for d in (first, second)}
    assert admin.delete(f"/api/v1/datasets/{first['id']}").status_code == 204
    assert ana.delete(f"/api/v1/datasets/{second['id']}").status_code == 204
    assert data_tables(db) == set()
    assert db.scalar(select(func.count()).select_from(DatasetColumn)) == 0
    gone = ana.get(f"/api/v1/datasets/{first['id']}")
    assert gone.status_code == 404 and gone.json()["code"] == "dataset_not_found"
    assert ana.delete(f"/api/v1/datasets/{first['id']}").status_code == 404
    actions = db.scalars(
        select(AuditLog.action).where(AuditLog.entity_type == "dataset").order_by(AuditLog.id)
    )
    assert list(actions) == ["dataset.created"] * 2 + ["dataset.updated"] + ["dataset.deleted"] * 2


def test_upload_errors(make_user, login, monkeypatch, db):
    make_user("ana")
    ana = login("ana")
    for content, code in [
        (b"", "empty_file"),
        (b"a,b\n", "empty_file"),
        (b"\xff\xfe\xff\xff", "bad_encoding"),
        (b"just_one\n1\n2\n", "too_few_columns"),
        (b"a,b\n1,2\n3,4,5,6\n", "bad_csv"),
    ]:
        response = upload(ana, content)
        assert response.status_code == 400 and response.json()["code"] == code, content

    monkeypatch.setattr(store, "MAX_BYTES", 1000)
    too_large = upload(ana)
    assert too_large.status_code == 400 and too_large.json()["code"] == "file_too_large"
    assert set(too_large.json()) == {"code", "message", "detail"}
    monkeypatch.setattr(store, "MAX_BYTES", 20 * 2**20)
    monkeypatch.setattr(store, "MAX_ROWS", 100)
    assert upload(ana).json() == {
        "code": "too_many_rows",
        "message": "Too many rows",
        "detail": {"limit": 100},
    }

    missing = ana.post("/api/v1/datasets", data={"name": "x"})
    assert missing.status_code == 422 and missing.json()["code"] == "validation_error"
    assert missing.json()["detail"][0]["field"] == "file"
    assert ana.get("/api/v1/datasets").json() == [] and data_tables(db) == set()


def test_failed_profiling_drops_the_new_table(make_user, login, monkeypatch, db):
    make_user("ana")
    ana = login("ana")

    def broken(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "profile", broken)
    with pytest.raises(RuntimeError):
        upload(ana)
    assert data_tables(db) == set()
    assert db.scalar(select(func.count()).select_from(Dataset)) == 0


def test_screening_ranks_features(make_user, login):
    make_user("ana")
    ana = login("ana")
    dataset = upload(ana).json()
    url = f"/api/v1/datasets/{dataset['id']}/screening"

    rows = ana.post(url, json={"method": "quantile", "bins": 5}).json()
    assert {r["column"] for r in rows} == FEATURES
    ivs = [r["iv"] for r in rows]
    assert all(iv is not None for iv in ivs) and ivs == sorted(ivs, reverse=True)
    assert {r["dtype"] for r in rows if r["column"] in ("city", "outcome", "responded")} == {"category"}
    assert all(r["trend"] == "unordered" for r in rows if r["dtype"] == "category")
    assert all(r["indicator_id"] is None for r in rows)
    income = next(r for r in rows if r["column"] == "income")
    assert income["bins"] == 6 and income["missing_rate"] == pytest.approx(loan_frame().income.isna().mean())

    created = ana.post(
        "/api/v1/indicators",
        json={"code": "income", "name": "收入", "dataset_id": dataset["id"], "column": "income"},
    ).json()
    flagged = {r["column"]: r["indicator_id"] for r in ana.post(url, json={"method": "tree"}).json()}
    assert flagged.pop("income") == created["id"] and set(flagged.values()) == {None}
    assert ana.get(f"/api/v1/datasets/{dataset['id']}").json()["indicator_count"] == 1
    assert ana.post(url, json={"bins": 1}).json()["code"] == "validation_error"


def test_datasets_require_sign_in(anon, make_user, login):
    make_user("ana")
    dataset = upload(login("ana")).json()
    url = f"/api/v1/datasets/{dataset['id']}"
    for response in (
        anon.get("/api/v1/datasets"),
        upload(anon),
        anon.get(url),
        anon.patch(url, json={"name": "x"}),
        anon.get(f"{url}/preview"),
        anon.post(f"{url}/screening", json={}),
        anon.delete(url),
    ):
        assert response.status_code == 401 and response.json()["code"] == "unauthenticated"


def test_seed_datasets_is_idempotent(make_user, db):
    owner = make_user("root", Role.admin)
    assert seed_datasets(db, owner, as_of=date(2026, 11, 19)) == [RETAIL, "12 indicators", BANK]

    datasets = {d.name: d for d in db.scalars(select(Dataset))}
    assert set(datasets) == {RETAIL, BANK} and all(d.source == "demo" for d in datasets.values())
    retail, bank = datasets[RETAIL], datasets[BANK]
    assert retail.target_column == "target" and retail.date_column and len(retail.profile["monthly"]) == 12
    assert (bank.target_column, bank.date_column, bank.row_count) == ("target", None, 4521)
    bank_columns = {c.column_name: c for c in bank.columns}
    assert bank_columns["month"].dtype == "category" and bank_columns["default"].role == "feature"
    indicators = db.scalars(select(Indicator)).unique().all()
    assert len(indicators) == 12
    assert all(i.status == "published" and i.dataset_id == retail.id for i in indicators)
    assert all(i.default_scheme is not None and i.default_scheme.iv > 0 for i in indicators)
    assert data_tables(db) == {retail.table_name, bank.table_name}

    assert seed_datasets(db, owner) == []
    assert db.scalar(select(func.count()).select_from(Dataset)) == 2
    assert db.scalar(select(func.count()).select_from(Indicator)) == 12
    assert db.scalar(select(func.count()).select_from(BinningScheme)) == 12
    assert len(data_tables(db)) == 2


def test_low_cardinality_numeric_gets_one_bin_per_value():
    import numpy as np
    import pandas as pd

    from kivi_ui.analytics.binning import BinSpec, fit, report
    from kivi_ui.data.store import quick_spec

    rng = np.random.default_rng(3)
    flag = pd.Series(rng.integers(0, 2, 400))
    target = pd.Series((rng.random(400) < np.where(flag == 1, 0.3, 0.05)).astype(int))
    spec = quick_spec(flag, "numeric", BinSpec(method="quantile", bins=5))
    assert spec.method == "manual" and spec.cuts == [0.5]
    rule, _ = fit(flag, target, spec, "numeric")
    assert report(rule, flag, target)["iv"] > 0.1
    many = pd.Series(rng.normal(size=400))
    assert quick_spec(many, "numeric", BinSpec(method="quantile")).method == "quantile"


def test_chinese_target_header_is_detected():
    import pandas as pd

    from kivi_ui.data import store

    frame = pd.DataFrame(
        {"客户号": [f"C{i}" for i in range(100)], "收入": range(100), "是否违约": [0, 1] * 50}
    )
    data, meta = store.normalise(frame)
    roles = store.guess_roles(data, meta)
    target = next(m["column_name"] for m in meta if m["name"] == "是否违约")
    assert roles["target_column"] == target and roles["target_event"] is None
