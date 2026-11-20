import pytest
from conftest import loan_frame, upload
from sqlalchemy import func, select

from kivi_ui.analytics.binning import NUMERIC_METHODS
from kivi_ui.models import BinningScheme, Indicator, Role

API = "/api/v1/indicators"


@pytest.fixture
def ana(make_user, login):
    make_user("ana")
    return login("ana")


@pytest.fixture
def dataset(ana):
    response = upload(ana)
    assert response.status_code == 201
    return response.json()


def create(c, dataset, column, code=None, **fields):
    body = {"code": code or column, "name": column, "dataset_id": dataset["id"], "column": column} | fields
    return c.post(API, json=body)


def test_create_from_a_dataset_column(ana, dataset):
    response = create(ana, dataset, "income", name=" 月收入 ", name_en="Income", category="basic", unit="cny")
    assert response.status_code == 201, response.json()
    income = response.json()
    assert (income["code"], income["name"], income["kind"]) == ("income", "月收入", "numeric")
    assert (income["category"], income["unit"], income["status"]) == ("basic", "cny", "draft")
    assert income["column_name"] == "income" and income["dataset"]["id"] == dataset["id"]
    assert income["owner"]["username"] == "ana"
    [scheme] = income["schemes"]
    assert income["default_scheme"]["id"] == scheme["id"] and scheme["name"] == "default"
    assert scheme["method"] == "monotonic" and scheme["spec"]["method"] == "monotonic"
    assert scheme["iv"] > 0.1 and scheme["trend"] in ("increasing", "decreasing")
    assert scheme["rule"]["kind"] == "numeric" and scheme["dataset_id"] == dataset["id"]
    assert sum(b["count"] for b in scheme["bins"]) == 240

    city = create(ana, dataset, "city").json()
    assert city["kind"] == "category" and city["default_scheme"]["method"] == "category"
    assert {b["kind"] for b in city["schemes"][0]["bins"]} == {"category", "missing"}
    # The original header works as the column reference too.
    age = create(ana, dataset, "年龄", code="Age").json()
    assert (age["code"], age["column_name"]) == ("age", "c8")
    assert ana.get(f"/api/v1/datasets/{dataset['id']}").json()["indicator_count"] == 3
    assert ana.get(f"{API}/{income['id']}").json() == income


def test_create_rejections(ana, dataset):
    assert create(ana, dataset, "income").status_code == 201
    taken = create(ana, dataset, "city", code="income")
    assert taken.status_code == 409 and taken.json()["code"] == "code_taken"
    for column in ("target", "apply_date", "id"):
        response = create(ana, dataset, column, code=f"x_{column}")
        assert response.status_code == 400 and response.json()["code"] == "not_a_feature"
        assert response.json()["detail"] == {"column": column}
    assert create(ana, dataset, "nope").json()["code"] == "unknown_column"
    assert create(ana, dataset, "city", code="9lives").json()["code"] == "validation_error"
    missing = create(ana, dataset | {"id": "00000000-0000-0000-0000-000000000000"}, "city")
    assert missing.status_code == 404 and missing.json()["code"] == "dataset_not_found"
    assert ana.get(f"{API}/00000000-0000-0000-0000-000000000000").json()["code"] == "indicator_not_found"


def test_import_derives_codes(ana, dataset, db):
    create(ana, dataset, "income")
    url = f"{API}/import"
    body = {
        "dataset_id": dataset["id"],
        "columns": ["income", "年龄", "city", "income"],
        "category": "credit",
    }
    response = ana.post(url, json=body)
    assert response.status_code == 201, response.json()
    created = response.json()
    assert [(i["code"], i["name"], i["column_name"]) for i in created] == [
        ("income_2", "income", "income"),
        ("c8", "年龄", "c8"),
        ("city", "city", "city"),
    ]
    assert all(i["category"] == "credit" and i["status"] == "draft" for i in created)
    assert all(i["default_scheme"]["iv"] > 0 for i in created)
    again = ana.post(url, json=body | {"columns": ["income"]}).json()
    assert [i["code"] for i in again] == ["income_3"]

    # A bad column fails the whole import.
    before = db.scalar(select(func.count()).select_from(Indicator))
    bad = ana.post(url, json=body | {"columns": ["outcome", "target"]})
    assert bad.status_code == 400 and bad.json()["code"] == "not_a_feature"
    assert ana.post(url, json=body | {"columns": ["outcome", "nope"]}).json()["code"] == "unknown_column"
    assert db.scalar(select(func.count()).select_from(Indicator)) == before
    assert ana.post(url, json=body | {"columns": []}).status_code == 422


def test_list_filters_and_counts(ana, dataset):
    create(ana, dataset, "income", category="basic", status="published", name_en="Monthly income")
    create(ana, dataset, "city", category="application")
    create(ana, dataset, "年龄", code="age", name="年龄", category="basic")
    other = upload(ana, name="other").json()
    create(ana, other, "responded", category="behavior")

    def page(**params):
        return ana.get(API, params=params).json()

    everything = page()
    assert everything["total"] == 4
    assert everything["counts"] == {"basic": 2, "application": 1, "behavior": 1}
    ivs = [i["default_scheme"]["iv"] for i in everything["items"]]
    assert ivs == sorted(ivs, reverse=True)

    basic = page(category="basic")
    assert {i["code"] for i in basic["items"]} == {"income", "age"} and basic["total"] == 2
    assert basic["counts"] == everything["counts"]  # counts ignore the category filter
    assert [i["code"] for i in page(q="INC")["items"]] == ["income"]
    assert [i["code"] for i in page(q="monthly")["items"]] == ["income"]  # English name
    assert [i["code"] for i in page(q="年龄")["items"]] == ["age"]
    published = page(status="published")
    assert published["total"] == 1 and published["counts"] == {"basic": 1}
    scoped = page(dataset_id=other["id"])
    assert [i["code"] for i in scoped["items"]] == ["responded"] and scoped["counts"] == {"behavior": 1}
    assert page(q="nothing") == {"items": [], "total": 0, "counts": {}}


@pytest.mark.parametrize("method", [m for m in NUMERIC_METHODS if m != "manual"])
def test_binning_preview_for_each_method(ana, dataset, db, method):
    income = create(ana, dataset, "income").json()
    response = ana.post(f"{API}/{income['id']}/binning", json={"method": method, "bins": 4})
    assert response.status_code == 200, response.json()
    result = response.json()
    intervals = [b for b in result["bins"] if b["kind"] == "interval"]
    assert 2 <= len(intervals) <= 4 and len(result["rule"]["cuts"]) == len(intervals) - 1
    assert sum(b["count"] for b in result["bins"]) == result["rows"] == 240
    assert result["iv"] == pytest.approx(sum(b["iv"] for b in result["bins"]), abs=1e-5)
    assert result["missing_rate"] == pytest.approx(loan_frame().income.isna().mean())
    assert result["bad_rate"] == pytest.approx(dataset["bad_rate"], abs=1e-6)
    assert isinstance(result["notes"], list)
    assert db.scalar(select(func.count()).select_from(BinningScheme)) == 1  # previews are not saved


def test_binning_preview_rules(ana, dataset):
    income = create(ana, dataset, "income").json()
    url = f"{API}/{income['id']}/binning"
    manual = ana.post(url, json={"method": "manual", "cuts": [16000, 8000, 12000]}).json()
    assert manual["rule"]["cuts"] == [8000, 12000, 16000]
    bounds = [(b["lower"], b["upper"]) for b in manual["bins"] if b["kind"] == "interval"]
    assert bounds == [(None, 8000), (8000, 12000), (12000, 16000), (16000, None)]
    assert ana.post(url, json={"method": "manual"}).json()["code"] == "validation_error"

    mismatch = ana.post(url, json={"method": "category"})
    assert mismatch.status_code == 400 and mismatch.json()["code"] == "method_mismatch"

    lowest = loan_frame().income.min()
    first = ana.post(url, json={"method": "quantile", "special": [lowest]}).json()["bins"][0]
    assert (first["code"], first["kind"], first["value"], first["count"]) == ("s0", "special", lowest, 1)

    city = create(ana, dataset, "city").json()
    result = ana.post(f"{API}/{city['id']}/binning", json={"method": "tree", "min_bin_share": 0.3}).json()
    assert result["rule"]["kind"] == "category" and result["trend"] == "unordered"
    # Only "south" reaches the share, so the two largest levels are kept.
    assert [b["code"] for b in result["bins"]] == ["c:east", "c:south", "other", "missing"]


def test_schemes_and_defaults(ana, dataset):
    income = create(ana, dataset, "income").json()
    url = f"{API}/{income['id']}"
    original = income["default_scheme"]["id"]

    quantile = ana.post(
        f"{url}/schemes",
        json={"name": " q4 ", "spec": {"method": "quantile", "bins": 4}, "make_default": False},
    )
    assert quantile.status_code == 201, quantile.json()
    quantile = quantile.json()
    assert (quantile["name"], quantile["method"], quantile["author"]["username"]) == ("q4", "quantile", "ana")
    assert len(quantile["rule"]["cuts"]) == 3
    assert ana.get(url).json()["default_scheme"]["id"] == original

    tree = ana.post(f"{url}/schemes", json={"name": "tree", "spec": {"method": "tree"}}).json()
    detail = ana.get(url).json()
    assert detail["default_scheme"]["id"] == tree["id"]
    assert [s["name"] for s in detail["schemes"]] == ["tree", "q4", "default"]  # newest first

    chosen = ana.post(f"{url}/schemes/{quantile['id']}/default").json()
    assert chosen["default_scheme"]["id"] == quantile["id"]
    # Deleting the default falls back to another scheme; deleting the others leaves none.
    after = ana.delete(f"{url}/schemes/{quantile['id']}").json()
    assert after["default_scheme"]["id"] == tree["id"]
    assert [s["id"] for s in after["schemes"]] == [tree["id"], original]
    assert ana.delete(f"{url}/schemes/{original}").json()["default_scheme"]["id"] == tree["id"]
    empty = ana.delete(f"{url}/schemes/{tree['id']}").json()
    assert empty["default_scheme"] is None and empty["schemes"] == []
    assert ana.get(f"{url}/stability").json()["code"] == "scheme_not_found"

    # A new scheme on an indicator without one becomes the default even when not asked.
    again = ana.post(f"{url}/schemes", json={"name": "q", "spec": {}, "make_default": False}).json()
    assert ana.get(url).json()["default_scheme"]["id"] == again["id"]

    city = create(ana, dataset, "city").json()
    foreign = city["default_scheme"]["id"]
    for response in (
        ana.post(f"{url}/schemes/{foreign}/default"),
        ana.delete(f"{url}/schemes/{foreign}"),
        ana.get(f"{url}/stability", params={"scheme_id": foreign}),
    ):
        assert response.status_code == 404 and response.json()["code"] == "scheme_not_found"
    assert ana.post(f"{url}/schemes", json={"name": "", "spec": {}}).status_code == 422


def test_stability_compares_months_with_the_reference(ana, dataset):
    income = create(ana, dataset, "income").json()
    url = f"{API}/{income['id']}/stability"

    result = ana.get(url).json()
    assert result["scheme_id"] == income["default_scheme"]["id"]
    months = result["months"]
    assert [m["month"] for m in months] == [f"2026-{m:02d}" for m in range(1, 7)]
    assert [m["in_reference"] for m in months] == [True] * 3 + [False] * 3
    assert result["reference"] == ["2026-01", "2026-03"]
    assert all(m["rows"] == 40 and sum(m["shares"].values()) == pytest.approx(1) for m in months)
    assert all(m["bad_rate"] is not None and m["psi"] >= 0 for m in months)
    # Income jumps in the last two months.
    assert min(m["psi"] for m in months[4:]) > max(0.25, *(m["psi"] for m in months[:4]))
    assert [b["code"] for b in result["bins"]] == [b["code"] for b in income["schemes"][0]["bins"]]

    quantile = ana.post(
        f"{API}/{income['id']}/schemes",
        json={"name": "q", "spec": {"method": "quantile"}, "make_default": False},
    ).json()
    short = ana.get(url, params={"scheme_id": quantile["id"], "reference_months": 2}).json()
    assert short["scheme_id"] == quantile["id"] and short["reference"] == ["2026-01", "2026-02"]
    assert [m["in_reference"] for m in short["months"]] == [True] * 2 + [False] * 4
    capped = ana.get(url, params={"reference_months": 60}).json()
    assert sum(m["in_reference"] for m in capped["months"]) == 5  # the last month is always compared
    assert ana.get(url, params={"reference_months": 0}).status_code == 422


def test_stability_needs_dates_over_two_months(ana, dataset):
    income = create(ana, dataset, "income").json()
    ana.patch(f"/api/v1/datasets/{dataset['id']}", json={"clear": ["date_column"]})
    response = ana.get(f"{API}/{income['id']}/stability")
    assert response.status_code == 400 and response.json()["code"] == "no_date_column"

    frame = loan_frame().assign(apply_date="2026-03-15")
    single = upload(ana, frame.to_csv(index=False).encode(), name="one month").json()
    city = create(ana, single, "city").json()
    assert ana.get(f"{API}/{city['id']}/stability").json()["code"] == "too_few_months"


def test_indicators_without_labels_or_source(ana, dataset):
    url = f"/api/v1/datasets/{dataset['id']}"
    ana.patch(url, json={"clear": ["target_column"]})
    unlabelled = create(ana, dataset, "income").json()
    assert unlabelled["default_scheme"] is None and unlabelled["schemes"] == []
    no_target = ana.post(f"{API}/{unlabelled['id']}/binning", json={})
    assert no_target.status_code == 400 and no_target.json()["code"] == "no_target"

    ana.patch(url, json={"target_column": "target"})
    labelled = create(ana, dataset, "city").json()
    assert ana.delete(url).status_code == 204
    orphan = ana.get(f"{API}/{labelled['id']}").json()
    assert orphan["dataset"] is None and orphan["schemes"][0]["dataset_id"] is None
    assert orphan["default_scheme"]["id"] == labelled["default_scheme"]["id"]  # history is kept
    gone = ana.post(f"{API}/{labelled['id']}/binning", json={})
    assert gone.status_code == 400 and gone.json()["code"] == "dataset_missing"


def test_update_and_delete_permissions(ana, dataset, make_user, login, db):
    make_user("bob")
    make_user("root", Role.admin)
    bob, admin = login("bob"), login("root")
    income = create(ana, dataset, "income", unit="cny").json()
    city = create(ana, dataset, "city").json()
    url = f"{API}/{income['id']}"

    updated = bob.patch(url, json={"name": " 收入 ", "status": "published", "category": "basic"}).json()
    assert (updated["name"], updated["status"], updated["category"]) == ("收入", "published", "basic")
    assert updated["unit"] == "cny"  # fields left out are kept
    assert ana.patch(url, json={"clear_unit": True}).json()["unit"] is None
    assert ana.patch(url, json={"status": "deleted"}).status_code == 422

    denied = bob.delete(url)
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden"
    assert admin.delete(url).status_code == 204
    assert ana.get(url).status_code == 404
    assert ana.delete(f"{API}/{city['id']}").status_code == 204
    assert db.scalar(select(func.count()).select_from(BinningScheme)) == 0
    assert ana.get(API).json()["total"] == 0


def test_indicators_require_sign_in(anon, ana, dataset):
    income = create(ana, dataset, "income").json()
    url = f"{API}/{income['id']}"
    for response in (
        anon.get(API),
        create(anon, dataset, "city"),
        anon.post(f"{API}/import", json={"dataset_id": dataset["id"], "columns": ["city"]}),
        anon.get(url),
        anon.patch(url, json={"name": "x"}),
        anon.post(f"{url}/binning", json={}),
        anon.post(f"{url}/schemes", json={"name": "x", "spec": {}}),
        anon.get(f"{url}/stability"),
        anon.delete(url),
    ):
        assert response.status_code == 401 and response.json()["code"] == "unauthenticated"
