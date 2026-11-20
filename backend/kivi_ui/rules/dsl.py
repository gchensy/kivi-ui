"""The strategy rule language, defined and validated with Pydantic.

A strategy version holds ordered rules. Each rule has a condition tree of
``all``/``any`` groups over conditions ``{field, op, value}`` and a decision.
Fields are request variables (``age``), model outputs (``model:RETAIL_APP.score``
or ``.prob``) or anything else present in the evaluated data. Watchlist
membership uses ``in_list`` / ``not_in_list`` with a list code as the value.
"""

import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

Decision = Literal["pass", "review", "reject"]
Op = Literal[
    "eq",
    "ne",
    "gt",
    "ge",
    "lt",
    "le",
    "in",
    "not_in",
    "between",
    "is_null",
    "not_null",
    "in_list",
    "not_in_list",
]
SEVERITY: dict[str, int] = {"pass": 0, "review": 1, "reject": 2}
MODEL_FIELD = re.compile(r"^model:([A-Z][A-Z0-9_]{1,63})\.(score|prob)$")
NUMERIC_OPS = {"gt", "ge", "lt", "le"}


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=128)
    op: Op
    value: Any = None

    @model_validator(mode="after")
    def _value_shape(self) -> "Condition":
        self.field = self.field.strip()
        if self.field.lower().startswith("model:"):
            code, _, output = self.field[6:].partition(".")
            self.field = f"model:{code.strip().upper()}.{output.strip().lower()}"
            if not MODEL_FIELD.match(self.field):
                raise ValueError("model outputs look like model:CODE.score or model:CODE.prob")
        op, value = self.op, self.value
        if op in NUMERIC_OPS and not isinstance(value, int | float):
            raise ValueError(f"{op} needs a number")
        if op == "between" and not (
            isinstance(value, list | tuple)
            and len(value) == 2
            and all(isinstance(v, int | float) for v in value)
        ):
            raise ValueError("between needs [low, high]")
        if op in ("in", "not_in") and not (isinstance(value, list) and value):
            raise ValueError(f"{op} needs a non-empty list")
        if op in ("in_list", "not_in_list"):
            if not (isinstance(value, str) and value.strip()):
                raise ValueError(f"{op} needs a watchlist code")
            self.value = value.strip().upper()
        if op in ("eq", "ne") and (value is None or isinstance(value, list | dict)):
            raise ValueError(f"{op} needs a single value")
        if op in ("is_null", "not_null"):
            self.value = None
        if op == "between":
            low, high = sorted(float(v) for v in value)
            self.value = [low, high]
        return self


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["all", "any"] = "all"
    # At least one item: an empty "all" group would be true for every row.
    items: list[Annotated[Union[Condition, "Group"], Field(union_mode="left_to_right")]] = Field(
        min_length=1, max_length=50
    )


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=1, max_length=128)
    name_en: str | None = Field(None, max_length=128)
    enabled: bool = True
    decision: Decision = "reject"
    terminal: bool = Field(
        False, description="A hit decides immediately; later rules are ignored (whitelists)"
    )
    reason: str = Field("", max_length=64)
    when: Group


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_decision: Decision = "pass"
    rules: list[RuleSpec] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _unique_codes(self) -> "Definition":
        codes = [r.code for r in self.rules]
        duplicates = sorted({c for c in codes if codes.count(c) > 1})
        if duplicates:
            raise ValueError(f"duplicate rule codes: {', '.join(duplicates)}")
        return self


def conditions(group: Group):
    for item in group.items:
        if isinstance(item, Group):
            yield from conditions(item)
        else:
            yield item


def references(definition: Definition) -> dict[str, set[str]]:
    """Plain fields, models and watchlists that a definition reads (enabled rules only)."""
    fields, models, lists = set(), set(), set()
    for rule in definition.rules:
        if not rule.enabled:
            continue
        for c in conditions(rule.when):
            match = MODEL_FIELD.match(c.field)
            if match:
                models.add(match.group(1))
            else:
                fields.add(c.field)
            if c.op in ("in_list", "not_in_list"):
                lists.add(str(c.value))
    return {"fields": fields, "models": models, "lists": lists}


def list_fields(definition: Definition) -> set[str]:
    """Fields checked against a watchlist: identifiers, so stored and traced only masked."""
    return {
        c.field
        for rule in definition.rules
        for c in conditions(rule.when)
        if c.op in ("in_list", "not_in_list")
    }
