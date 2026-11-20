"""The strategy rule language and its vectorized engine: small hand-made frames, no API."""

import copy
import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from kivi_ui.analytics.sample import FEATURES, simulate
from kivi_ui.analytics.training import Candidate, TrainConfig, score_frame, train
from kivi_ui.routes.indicators import default_spec
from kivi_ui.rules.dsl import Condition, Definition, Group, references
from kivi_ui.rules.engine import (
    Context,
    ModelRuntime,
    RuleError,
    evaluate,
    make_hasher,
    mask_text,
    normalise_value,
    summarise,
    swap,
)

HASH = make_hasher("test-key")
T, F = True, False


def cond(field, op, value=None) -> dict:
    return {"field": field, "op": op, "value": value}


def group(*items, mode="all") -> dict:
    return {"mode": mode, "items": list(items)}


def rule(code, *items, decision="reject", mode="all", **extra) -> dict:
    return {
        "code": code,
        "name": f"rule {code}",
        "decision": decision,
        "when": group(*items, mode=mode),
    } | extra


def define(*rules, default="pass") -> Definition:
    return Definition.model_validate({"default_decision": default, "rules": list(rules)})


def run(frame, *rules, ctx=None, default="pass", trace=False):
    return evaluate(define(*rules, default=default), frame, ctx or Context(hasher=HASH), trace=trace)


def hits(frame, *items, mode="all", ctx=None) -> list[bool]:
    return run(frame, rule("R", *items, mode=mode), ctx=ctx).hits["R"].tolist()


# ---- The DSL ----------------------------------------------------------------------------------

MALFORMED = [
    ("gt", "10"),
    ("ge", None),
    ("lt", [1]),
    ("le", {"value": 1}),
    ("between", [1]),
    ("between", [1, 2, 3]),
    ("between", [1, "9"]),
    ("between", 5),
    ("in", []),
    ("in", "east"),
    ("not_in", None),
    ("in_list", ""),
    ("in_list", 7),
    ("not_in_list", ["BL"]),
    ("eq", None),
    ("eq", [1]),
    ("ne", {"a": 1}),
    ("like", "x"),
]


@pytest.mark.parametrize(("op", "value"), MALFORMED)
def test_malformed_conditions_are_rejected(op, value):
    bad = cond("age", op, value)
    with pytest.raises(ValidationError):
        Condition.model_validate(bad)
    # The item union falls back to Group, which must not swallow a bad condition as an empty group.
    with pytest.raises(ValidationError):
        Group.model_validate(group(bad))
    with pytest.raises(ValidationError):
        define(rule("R1", cond("age", "not_null"), group(cond("city", "eq", "x"), bad, mode="any")))


def test_condition_fields_are_required():
    for bad in (cond("", "eq", 1), {"op": "eq", "value": 1}, {"field": "age", "value": 1}):
        with pytest.raises(ValidationError):
            Group.model_validate(group(bad))
    with pytest.raises(ValidationError):
        Condition.model_validate(cond("x" * 129, "eq", 1))


@pytest.mark.parametrize(
    "payload",
    [
        {"rules": [], "version": 2},
        {"default_decision": "approve"},
        {"rules": [rule("R1", cond("a", "eq", 1), then={"decision": "reject"})]},
        {"rules": [rule("R1", cond("a", "eq", 1) | {"weight": 2})]},
        {"rules": [rule("R1", group(cond("a", "eq", 1)) | {"negate": True})]},
        {"rules": [rule("R1", cond("a", "eq", 1), decision="block")]},
        {"rules": [rule("R1", cond("a", "eq", 1), mode="xor")]},
        {"rules": [rule("R 1", cond("a", "eq", 1))]},
        {"rules": [rule("R1", cond("a", "eq", 1), name="")]},
        {"rules": [rule("R1", cond("a", "eq", 1)) | {"when": None}]},
    ],
)
def test_unknown_keys_and_values_are_rejected(payload):
    with pytest.raises(ValidationError):
        Definition.model_validate(payload)


def test_empty_groups_and_bad_model_references_are_rejected():
    for bad in (group(), group(group(cond("a", "eq", 1)), {}), group(group(mode="any"))):
        with pytest.raises(ValidationError):
            Group.model_validate(bad)
    for field in ("model:SC_A", "model:SC_A.pd", "model:.score", "MODEL:9X.score"):
        with pytest.raises(ValidationError, match="model:CODE.score"):
            Condition.model_validate(cond(field, "lt", 1))
    assert Condition.model_validate(cond(" Model:sc_a.Prob ", "gt", 0.5)).field == "model:SC_A.prob"
    assert Condition.model_validate(cond("phone", "in_list", " bl_phone ")).value == "BL_PHONE"


def test_rule_codes_are_unique():
    rules = [rule(code, cond("a", "eq", 1)) for code in ("R1", "R2", "R1", "R3", "R2")]
    with pytest.raises(ValidationError, match="duplicate rule codes: R1, R2"):
        define(*rules)
    assert [r.code for r in define(*rules[:2]).rules] == ["R1", "R2"]


def test_values_are_normalised_and_groups_nest():
    assert Condition.model_validate(cond("age", "between", [60, 20])).value == [20.0, 60.0]
    assert Condition.model_validate(cond("age", "is_null", 5)).value is None
    assert Condition.model_validate(cond("age", "not_null", "x")).value is None
    parsed = define(rule("R1", cond("a", "eq", 1), group(cond("b", "gt", 2), group(cond("c", "is_null")))))
    [outer] = parsed.rules
    first, nested = outer.when.items
    assert isinstance(first, Condition) and isinstance(nested, Group) and nested.mode == "all"
    assert isinstance(nested.items[1], Group) and nested.items[1].items[0].op == "is_null"
    assert (
        outer.enabled
        and not outer.terminal
        and outer.decision == "reject"
        and parsed.default_decision == "pass"
    )
    # Round trip: what is stored is what is validated again on the next load.
    assert Definition.model_validate(parsed.model_dump()) == parsed


def test_references_ignore_disabled_rules():
    definition = define(
        rule("W1", cond("phone", "in_list", "WL"), decision="pass", terminal=True),
        rule(
            "R1",
            cond("model:SC_A.score", "lt", 500),
            group(cond("age", "lt", 20), cond("device", "not_in_list", "DEV"), mode="any"),
        ),
        rule(
            "R2",
            cond("model:OTHER.prob", "gt", 0.5),
            cond("ip", "in_list", "IP"),
            cond("income", "is_null"),
            enabled=False,
        ),
        rule("R3", cond("model:sc_a.score", "lt", 1)),  # normalised to model:SC_A.score
    )
    assert definition.rules[3].when.items[0].field == "model:SC_A.score"
    assert references(definition) == {
        "fields": {"phone", "age", "device"},
        "models": {"SC_A"},
        "lists": {"WL", "DEV"},
    }
    assert references(Definition()) == {"fields": set(), "models": set(), "lists": set()}


# ---- Operators ---------------------------------------------------------------------------------


@pytest.fixture
def people() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "age": [18, 25, 40, np.nan, 61],
            "city": ["east", " north ", None, "", "south"],
            "code": ["1", "2", "x", None, "01"],
        }
    )


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (cond("age", "eq", 25), [F, T, F, F, F]),
        (cond("age", "eq", 25.0), [F, T, F, F, F]),
        (cond("age", "ne", 25), [T, F, T, F, T]),
        (cond("age", "gt", 25), [F, F, T, F, T]),
        (cond("age", "ge", 25), [F, T, T, F, T]),
        (cond("age", "lt", 25), [T, F, F, F, F]),
        (cond("age", "le", 25), [T, T, F, F, F]),
        (cond("age", "between", [25, 61]), [F, T, T, F, T]),
        (cond("age", "between", [61, 25]), [F, T, T, F, T]),
        (cond("age", "between", [18, 18]), [T, F, F, F, F]),
        (cond("age", "in", [18, 61]), [T, F, F, F, T]),
        (cond("age", "not_in", [18, 61]), [F, T, T, F, F]),
        # Text is trimmed and case-sensitive; null and blank never compare.
        (cond("city", "eq", "north"), [F, T, F, F, F]),
        (cond("city", "eq", "EAST"), [F, F, F, F, F]),
        (cond("city", "ne", "east"), [F, T, F, F, T]),
        (cond("city", "in", ["east", "north"]), [T, T, F, F, F]),
        (cond("city", "not_in", ["east"]), [F, T, F, F, T]),
        (cond("city", "gt", 0), [F, F, F, F, F]),
        # Numeric values compare numbers ("01" == 1); text values compare text.
        (cond("code", "eq", 1), [T, F, F, F, T]),
        (cond("code", "eq", "1"), [T, F, F, F, F]),
        (cond("code", "in", [1, 2]), [T, T, F, F, T]),
        (cond("code", "in", ["1", "2"]), [T, T, F, F, F]),
        (cond("code", "in", [1, "x"]), [T, F, T, F, F]),
        (cond("code", "ne", 1), [F, T, F, F, F]),
        (cond("code", "gt", 1), [F, T, F, F, F]),
        # is_null covers None, NaN and blank text.
        (cond("age", "is_null"), [F, F, F, T, F]),
        (cond("city", "is_null"), [F, F, T, T, F]),
        (cond("city", "not_null"), [T, T, F, F, T]),
        (cond("code", "not_null"), [T, T, T, F, T]),
    ],
)
def test_operators(people, condition, expected):
    assert hits(people, condition) == expected


def test_object_columns_and_blank_text():
    mixed = pd.DataFrame({"v": [5, None, "7", "  ", "seven"]})
    assert hits(mixed, cond("v", "gt", 4)) == [T, F, T, F, F]
    assert hits(mixed, cond("v", "is_null")) == [F, T, F, T, F]
    assert hits(mixed, cond("v", "ne", 5)) == [F, F, T, F, F]


def test_a_missing_field_is_null_and_reported(people):
    result = run(people, rule("R1", cond("score", "is_null")), rule("R2", cond("score", "lt", 1)))
    assert result.hits["R1"].all() and not result.hits["R2"].any()
    assert result.missing_fields == ["score"]
    result = run(people, rule("R1", cond("age", "not_null"), cond("b", "eq", 1), cond("a", "ne", 1)))
    assert result.missing_fields == ["a", "b"]


def test_nested_groups(people):
    young_east_or_old_south = group(
        group(cond("age", "lt", 20), cond("city", "eq", "east")),
        group(cond("age", "gt", 60), cond("city", "eq", "south")),
        mode="any",
    )
    assert hits(people, young_east_or_old_south) == [T, F, F, F, T]
    adult_and_either = [
        cond("age", "ge", 20),
        group(cond("city", "in", ["north", "south"]), cond("code", "eq", "x"), mode="any"),
    ]
    assert hits(people, *adult_and_either) == [F, T, T, F, T]
    young_or_south_one = [cond("age", "lt", 20), group(cond("city", "eq", "south"), cond("code", "eq", 1))]
    assert hits(people, *young_or_south_one, mode="any") == [T, F, F, F, T]
    assert hits(people, *young_or_south_one) == [F, F, F, F, F]


# ---- Combining rules into a decision ----------------------------------------------------------


def test_the_most_severe_hit_wins_and_ties_go_to_the_earliest_rule():
    frame = pd.DataFrame({"x": [1, 2, 3, 4, 5]})
    result = run(
        frame,
        rule("A", cond("x", "ge", 2), decision="review"),
        rule("B", cond("x", "ge", 3)),
        rule("C", cond("x", "ge", 3)),
        rule("D", cond("x", "eq", 1), decision="pass"),
        rule("E", cond("x", "ge", 1), enabled=False),
        rule("F", cond("x", "eq", 4), decision="review"),
        default="review",
    )
    assert result.decision.tolist() == ["pass", "review", "reject", "reject", "reject"]
    assert result.deciding_rule.tolist() == ["D", "A", "B", "B", "B"]
    assert list(result.hits.columns) == ["A", "B", "C", "D", "F"]  # disabled rules are not evaluated
    assert result.hits.loc[3].tolist() == [T, T, T, F, T]  # every hit is kept, not just the decisive one

    # Order does not matter for severity, only for ties.
    swapped = run(frame, rule("C", cond("x", "ge", 3)), rule("A", cond("x", "ge", 2), decision="review"))
    assert swapped.decision.tolist() == ["pass", "review", "reject", "reject", "reject"]
    assert swapped.deciding_rule.tolist() == ["", "A", "C", "C", "C"]


def test_the_default_decision_applies_without_a_hit():
    frame = pd.DataFrame({"x": [1, 2]})
    for default in ("pass", "review", "reject"):
        result = run(frame, rule("A", cond("x", "gt", 5)), default=default)
        assert result.decision.tolist() == [default, default]
        assert result.deciding_rule.tolist() == ["", ""]
    nothing = evaluate(Definition(default_decision="review"), frame, Context())
    assert nothing.decision.tolist() == ["review", "review"] and nothing.hits.empty


def test_a_terminal_whitelist_overrides_a_reject():
    ctx = Context(
        lists={"WL": frozenset(map(HASH, ["111", "222"])), "BL": frozenset(map(HASH, ["111", "333"]))},
        hasher=HASH,
    )
    frame = pd.DataFrame({"phone": ["111", "222", "333", "444"], "age": [30, 17, 17, 30]})
    result = run(
        frame,
        rule("R00", cond("age", "lt", 18)),
        rule("W01", cond("phone", "in_list", "WL"), decision="pass", terminal=True),
        rule("R01", cond("phone", "in_list", "BL")),
        rule("T02", cond("phone", "eq", "111"), decision="review", terminal=True),
        ctx=ctx,
    )
    # A terminal hit decides on its own: later rules (even terminal ones) and earlier
    # non-terminal hits do not change it.
    assert result.decision.tolist() == ["pass", "pass", "reject", "pass"]
    assert result.deciding_rule.tolist() == ["W01", "W01", "R00", ""]
    assert result.hits.loc[0].tolist() == [F, T, T, T]
    assert result.hits.loc[1].tolist() == [T, T, F, F]


def test_disabled_rules_need_nothing():
    frame = pd.DataFrame({"x": [1]})
    result = run(
        frame,
        rule("A", cond("phone", "in_list", "NOPE"), enabled=False),
        rule("B", cond("model:NOPE.score", "lt", 1), enabled=False),
        rule("C", cond("x", "eq", 1), decision="review"),
        ctx=Context(),
    )
    assert result.decision.tolist() == ["review"] and list(result.hits.columns) == ["C"]
    assert result.outputs.empty and result.missing_fields == []


# ---- Watchlists ----------------------------------------------------------------------------------


def test_normalise_mask_and_hash():
    assert normalise_value(13800000000.0) == "13800000000"
    assert normalise_value(np.float64(5.0)) == normalise_value(np.int64(5)) == normalise_value("5") == "5"
    assert normalise_value(1.5) == "1.5"
    assert normalise_value("  ab-c 1 ") == "ABC1"
    phone = {
        "13800138000",
        " 138 0013 8000",
        "138-0013-8000\t",
        "138 - 0013 - 8000",
        "138\u30000013\u30008000",
    }
    assert {normalise_value(v) for v in phone} == {"13800138000"}
    for empty in (None, np.nan, pd.NA, "", "   "):
        assert normalise_value(empty) is None

    assert mask_text("13800001234") == "138****1234"
    assert mask_text("110101199001011234") == "110***********1234"
    assert mask_text("ABCDE") == "A***E"
    assert mask_text("ABC") == "***"

    digest = HASH("13800001234")
    assert len(digest) == 64 and digest == make_hasher("test-key")("13800001234")
    assert digest != make_hasher("other-key")("13800001234") and digest != HASH("13800001235")
    assert digest != hashlib.sha256(b"13800001234").hexdigest()  # keyed, not a plain digest


def test_watchlist_membership_after_normalisation():
    # Lists hold digests of normalised values, as the API stores them.
    ctx = Context(lists={"BL": frozenset(map(HASH, ["13800000000", "ABC1"]))}, hasher=HASH)
    as_float = pd.DataFrame({"phone": [13800000000.0, np.nan, 13900000000.0]})
    assert hits(as_float, cond("phone", "in_list", "BL"), ctx=ctx) == [T, F, F]
    assert hits(as_float, cond("phone", "not_in_list", "BL"), ctx=ctx) == [
        F,
        F,
        T,
    ]  # null is not "not listed"
    as_int = pd.DataFrame({"phone": [13800000000, 13900000000]})
    assert hits(as_int, cond("phone", "in_list", "BL"), ctx=ctx) == [T, F]
    as_text = pd.DataFrame({"phone": [" 13800000000 ", "abc-1", "", None, "ABC-2"]})
    assert hits(as_text, cond("phone", "in_list", "BL"), ctx=ctx) == [T, T, F, F, F]
    assert hits(as_text, cond("phone", "not_in_list", "BL"), ctx=ctx) == [F, F, F, F, T]
    empty = Context(lists={"BL": frozenset()}, hasher=HASH)
    assert hits(as_text, cond("phone", "not_in_list", "BL"), ctx=empty) == [T, T, F, F, T]


def test_missing_lists_models_and_hasher_are_errors():
    frame = pd.DataFrame({"phone": ["1"]})
    with pytest.raises(RuleError) as error:
        run(frame, rule("R1", cond("phone", "in_list", "NOPE")), ctx=Context(hasher=HASH))
    assert (error.value.code, error.value.detail) == ("list_not_found", {"list": "NOPE"})
    with pytest.raises(RuleError) as error:
        run(frame, rule("R1", cond("phone", "not_in_list", "BL")), ctx=Context(lists={"BL": frozenset()}))
    assert error.value.code == "list_unavailable"
    with pytest.raises(RuleError) as error:
        run(frame, rule("R1", cond("phone", "eq", "1")), rule("R2", cond("model:SC.prob", "gt", 0.1)))
    assert (error.value.code, error.value.detail) == ("model_not_online", {"model": "SC"})


# ---- Model outputs ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    return simulate(date(2026, 11, 19))


@pytest.fixture(scope="module")
def scorecard(sample) -> ModelRuntime:
    chosen = [
        f for f in FEATURES if f.name in ("overdue_24m", "inquiries_6m", "debt_ratio", "age", "channel")
    ]
    candidates = [
        Candidate(f.name, f.name, f.zh, f.en, f.name, f.kind, f.unit, default_spec(f.kind).model_dump())
        for f in chosen
    ]
    result = train(sample, sample.target, sample.applied_on, candidates, TrainConfig())
    assert len(result["features"]) >= 3
    return ModelRuntime("SC", "00000000-0000-0000-0000-000000000001", 1, result)


def test_model_outputs_score_the_online_version(sample, scorecard):
    rows = sample.head(400).reset_index(drop=True)
    expected = score_frame(scorecard.result, rows)
    cut = int(expected.score.median())

    def quantile(q: float) -> float:
        return float(expected.probability.quantile(q))

    ctx = Context(models={"SC": scorecard}, hasher=HASH)
    result = run(
        rows,
        rule("LOW", cond("model:SC.score", "lt", cut)),
        rule("GREY", cond("model:SC.prob", "between", [quantile(0.2), quantile(0.45)]), decision="review"),
        ctx=ctx,
    )
    assert list(result.outputs.columns) == ["model:SC.score", "model:SC.prob"]
    assert result.outputs["model:SC.score"].tolist() == expected.score.tolist()
    assert result.outputs["model:SC.prob"].tolist() == expected.probability.tolist()
    assert result.hits["LOW"].tolist() == (expected.score < cut).tolist()
    assert 0 < result.hits["LOW"].sum() < len(rows) and result.missing_fields == []
    assert set(result.decision) == {"pass", "review", "reject"}

    # Features are found by column, uploaded header or indicator code.
    renamed = copy.deepcopy(scorecard.result)
    for i, feature in enumerate(renamed["features"]):
        feature["column"], feature["header"] = f"c{i}", f"头{i}" if i % 2 else None
    aliased = rows.rename(columns={f["code"]: f["header"] for f in renamed["features"] if f["header"]})
    ctx = Context(models={"SC": ModelRuntime("SC", "x", 1, renamed)})
    again = run(aliased, rule("LOW", cond("model:SC.score", "lt", cut)), ctx=ctx)
    assert again.outputs.equals(result.outputs) and again.missing_fields == []

    # A missing feature scores as missing and is reported by its code; the others still count.
    dropped = scorecard.result["features"][0]["code"]
    lacking = rows.drop(columns=[dropped])
    partial = run(
        lacking, rule("LOW", cond("model:SC.score", "lt", cut)), ctx=Context(models={"SC": scorecard})
    )
    assert partial.missing_fields == [dropped]
    expected = score_frame(scorecard.result, lacking.assign(**{dropped: np.nan}))
    assert partial.outputs["model:SC.score"].tolist() == expected.score.tolist()
    assert not partial.outputs.equals(result.outputs)


def as_record(frame: pd.DataFrame, i: int) -> dict:
    """The row as an API client would send it: JSON, nulls for missing values."""
    return json.loads(frame.iloc[[i]].to_json(orient="records"))[0]


def test_one_row_evaluates_like_the_same_row_in_a_frame(sample, scorecard):
    rows = (
        sample.head(500).drop(columns=["applied_on", "month", "month_index", "target"]).reset_index(drop=True)
    )
    rows.loc[::9, "age"] = np.nan
    rows.loc[::13, "channel"] = None
    phones = rows.phone.tolist()
    cut = int(score_frame(scorecard.result, rows).score.median())
    ctx = Context(
        models={"SC": scorecard},
        lists={"BL": frozenset(map(HASH, phones[::7])), "WL": frozenset(map(HASH, phones[::23]))},
        hasher=HASH,
    )
    definition = define(
        rule("W01", cond("phone", "in_list", "WL"), decision="pass", terminal=True),
        rule("R01", cond("phone", "in_list", "BL")),
        rule("R02", cond("age", "lt", 22), cond("age", "gt", 58), mode="any"),
        rule("R03", cond("model:SC.score", "lt", cut - 20)),
        rule(
            "R04",
            cond("channel", "in", ["partner"]),
            group(cond("monthly_income", "is_null"), cond("debt_ratio", "gt", 0.4), mode="any"),
            decision="review",
        ),
        rule("R05", cond("model:SC.score", "between", [cut - 20, cut]), decision="review"),
        rule("R06", cond("loan_term", "eq", "36"), cond("inquiries_6m", "ge", 5), cond("age", "not_null")),
        rule("R07", cond("channel", "is_null"), decision="review"),
    )
    # A stored dataset holds the phone as a number; API callers send text.
    frame = rows.assign(phone=rows.phone.astype(float))
    full = evaluate(definition, frame, ctx)
    chosen = set(range(0, 500, 9)[:3])  # rows with a missing age
    for code in full.hits.columns:
        chosen.update(full.hits.index[full.hits[code]][:2])
        chosen.update(full.deciding_rule.index[full.deciding_rule == code][:2])
    for decision in ("pass", "review", "reject"):
        chosen.update(full.decision.index[full.decision == decision][:2])
    # Every rule that decides anywhere in the frame is covered, and the rules differ in what they decide.
    assert set(full.deciding_rule[sorted(chosen)]) == set(full.deciding_rule)
    assert set(full.deciding_rule) >= {"W01", "R01", "R02", "R03", "R04", "R05", ""}
    for i in sorted(chosen):
        one = evaluate(definition, pd.DataFrame([as_record(rows, i)]), ctx)
        assert one.decision.iloc[0] == full.decision.iloc[i], i
        assert one.deciding_rule.iloc[0] == full.deciding_rule.iloc[i], i
        assert one.hits.iloc[0].tolist() == full.hits.iloc[i].tolist(), i
        assert one.outputs.iloc[0].tolist() == full.outputs.iloc[i].tolist(), i


# ---- Traces --------------------------------------------------------------------------------------


def test_the_trace_explains_the_first_row_and_masks_listed_values():
    ctx = Context(lists={"BL": frozenset({HASH("13800001234")})}, hasher=HASH)
    frame = pd.DataFrame([{"phone": 13800001234.0, "age": 17, "income": None, "city": "east"}])
    result = run(
        frame,
        rule("R01", cond("phone", "in_list", "BL"), name_en="Blacklisted"),
        rule(
            "R02",
            cond("age", "lt", 18),
            group(cond("income", "is_null"), cond("income", "lt", 1000), cond("nope", "eq", 1), mode="any"),
            decision="review",
        ),
        rule(
            "R03",
            cond("age", "between", [60, 99]),
            cond("city", "eq", "east"),
            terminal=True,
            decision="pass",
        ),
        ctx=ctx,
        trace=True,
    )
    r1, r2, r3 = result.trace
    assert r1 == {
        "code": "R01",
        "name": "rule R01",
        "name_en": "Blacklisted",
        "decision": "reject",
        "terminal": False,
        "hit": True,
        "when": {
            "mode": "all",
            "result": True,
            "items": [
                {"field": "phone", "op": "in_list", "value": "BL", "actual": "138****1234", "result": True}
            ],
        },
    }
    assert r2["hit"] and r2["when"]["items"][0] == {
        "field": "age",
        "op": "lt",
        "value": 18,
        "actual": 17,
        "result": True,
    }
    nested = r2["when"]["items"][1]
    assert (nested["mode"], nested["result"]) == ("any", True)
    assert [(n["op"], n["actual"], n["result"]) for n in nested["items"]] == [
        ("is_null", None, True),
        ("lt", None, False),
        ("eq", None, False),
    ]
    assert r3["hit"] is False and r3["terminal"] is True
    assert [n["result"] for n in r3["when"]["items"]] == [False, True]
    assert r3["when"]["items"][0]["value"] == [60.0, 99.0]
    text = json.dumps(result.trace)  # plain JSON values throughout
    assert "13800001234" not in text
    assert run(frame, rule("R01", cond("age", "lt", 18))).trace is None


# ---- Backtest summaries -------------------------------------------------------------------------


def test_summarise_counts_rates_and_exclusive_hits():
    frame = pd.DataFrame({"x": range(1, 11)})
    y = pd.Series([1, 1, 0, 1, 0, 0, 0, 1, 1, 0], dtype=float)
    months = pd.Series(["2026-01"] * 5 + ["2026-02"] * 2 + [None] + ["2026-02"] * 2, dtype="string")
    definition = define(
        rule("A", cond("x", "le", 3)),
        rule("B", cond("x", "between", [3, 5])),
        rule("C", cond("x", "ge", 9), decision="review"),
        rule("D", cond("x", "eq", 10), decision="pass"),
        rule("E", cond("x", "ge", 1), enabled=False),
    )
    result = evaluate(definition, frame, Context())
    assert result.decision.tolist() == ["reject"] * 5 + ["pass"] * 3 + ["review"] * 2
    summary = summarise(definition, result, y, months)
    assert {k: summary[k] for k in ("rows", "pass", "review", "reject", "missing_fields")} == {
        "rows": 10,
        "pass": 3,
        "review": 2,
        "reject": 5,
        "missing_fields": [],
    }
    assert (summary["pass_rate"], summary["review_rate"], summary["reject_rate"]) == (0.3, 0.2, 0.5)
    assert summary["bad_rate"] == 0.5
    assert summary["bad_rate_by_decision"] == {"pass": 0.333333, "review": 0.5, "reject": 0.6}
    rules = {r["code"]: r for r in summary["rules"]}
    # Exclusive: hit by no other blocking (review / reject) rule. Decisive: set the decision.
    assert {
        c: (r["hits"], r["hit_rate"], r["exclusive"], r["decisive"], r["bad_rate"]) for c, r in rules.items()
    } == {
        "A": (3, 0.3, 2, 3, 0.666667),
        "B": (3, 0.3, 2, 2, 0.333333),
        "C": (2, 0.2, 2, 2, 0.5),
        "D": (1, 0.1, 0, 0, 0.0),
        "E": (0, 0, 0, 0, None),
    }
    assert [r["enabled"] for r in summary["rules"]] == [True, True, True, True, False]
    assert summary["monthly"] == [
        {"month": "2026-01", "rows": 5, "pass_rate": 0.0, "reject_rate": 1.0, "pass_bad_rate": None},
        {"month": "2026-02", "rows": 4, "pass_rate": 0.5, "reject_rate": 0.0, "pass_bad_rate": 0.0},
    ]

    bare = summarise(definition, result, None, None)
    assert "bad_rate" not in bare and "monthly" not in bare
    assert all(r["bad_rate"] is None for r in bare["rules"])
    assert (
        summarise(Definition(), evaluate(Definition(), frame.head(0), Context()), None, None)["pass_rate"]
        is None
    )


def test_swap_cells():
    a = pd.Series(["pass", "pass", "reject", "review", "reject", "pass"])
    b = pd.Series(["pass", "reject", "reject", "pass", "review", "pass"])
    y = pd.Series([0, 1, 1, 0, 0, 1], dtype=float)
    cells = swap(a, b, y)
    assert [(c["from"], c["to"]) for c in cells] == [
        (x, z) for x in ("pass", "review", "reject") for z in ("pass", "review", "reject")
    ]
    table = {(c["from"], c["to"]): (c["rows"], c["bad_rate"]) for c in cells}
    assert table[("pass", "pass")] == (2, 0.5)
    assert table[("pass", "reject")] == (1, 1.0)
    assert table[("review", "pass")] == (1, 0.0)
    assert table[("reject", "review")] == (1, 0.0)
    assert table[("reject", "reject")] == (1, 1.0)
    assert table[("review", "review")] == (0, None)
    assert sum(rows for rows, _ in table.values()) == len(a)
    assert all(c["bad_rate"] is None for c in swap(a, b, None))
