"""Indicator catalogue, interactive binning, saved schemes and stability."""

import uuid

import pandas as pd
from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..analytics import binning
from ..analytics.binning import BinningError, BinSpec
from ..data import store
from ..data_schemas import (
    BinningOut,
    IndicatorCreateIn,
    IndicatorDetail,
    IndicatorImportIn,
    IndicatorOut,
    IndicatorPage,
    IndicatorUpdateIn,
    SchemeCreateIn,
    SchemeOut,
    StabilityMonth,
    StabilityOut,
)
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..models import BinningScheme, Dataset, DatasetColumn, Indicator, User
from .datasets import ensure_owner, get_dataset

router = APIRouter(prefix="/indicators", tags=["indicators"])


def get_indicator(db: Db, indicator_id: uuid.UUID) -> Indicator:
    indicator = db.get(Indicator, indicator_id)
    if indicator is None:
        raise ApiError(404, "indicator_not_found", "Indicator not found")
    return indicator


def source(db: Session, indicator: Indicator) -> Dataset:
    if indicator.dataset is None:
        raise ApiError(400, "dataset_missing", "The indicator's source dataset was deleted")
    return indicator.dataset


def labelled(db: Session, dataset: Dataset, column: str) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Feature values and 0/1 labels for rows with a label, plus the raw frame."""
    if not dataset.target_column:
        raise store.DataError("no_target", "Choose the target column of this dataset first")
    columns = [column, dataset.target_column]
    if dataset.date_column:
        columns.append(dataset.date_column)
    frame = store.read_columns(db, dataset, columns)
    y = store.labels(dataset, frame)
    keep = y.notna()
    return frame[column][keep], y[keep].astype(int), frame[keep]


def run_binning(db: Session, indicator: Indicator, spec: BinSpec) -> tuple[binning.Rule, dict, list[str]]:
    dataset = source(db, indicator)
    values, target, _ = labelled(db, dataset, indicator.column_name)
    if indicator.kind == "category":
        spec = spec.model_copy(update={"method": "category"})
    elif spec.method == "category":
        raise BinningError("method_mismatch", "Use a numeric method for a numeric indicator")
    rule, notes = binning.fit(values, target, spec, indicator.kind)
    return rule, binning.report(rule, values, target), notes


def default_spec(kind: str) -> BinSpec:
    return (
        BinSpec(method="category", min_bin_share=0.02) if kind == "category" else BinSpec(method="monotonic")
    )


def save_scheme(
    db: Session, indicator: Indicator, name: str, spec: BinSpec, user: User | None, make_default: bool
) -> BinningScheme:
    try:
        rule, result, _ = run_binning(db, indicator, spec)
    except BinningError:
        if spec.method != "monotonic":
            raise
        spec = BinSpec(method="quantile")
        rule, result, _ = run_binning(db, indicator, spec)
    scheme = BinningScheme(
        indicator_id=indicator.id,
        dataset_id=indicator.dataset_id,
        name=name,
        method="category" if indicator.kind == "category" else spec.method,
        spec=spec.model_dump(),
        rule=rule.to_dict(),
        bins=result["bins"],
        iv=result["iv"],
        trend=result["trend"],
        missing_rate=result["missing_rate"],
        created_by=user.id if user else None,
    )
    db.add(scheme)
    db.flush()
    if make_default or indicator.default_scheme_id is None:
        indicator.default_scheme_id = scheme.id
    return scheme


def new_indicator(
    db: Session,
    dataset: Dataset,
    column: DatasetColumn,
    *,
    code: str,
    name: str,
    owner: User | None,
    **fields,
) -> Indicator:
    if column.dtype not in ("numeric", "category") or column.role != "feature":
        raise ApiError(
            400,
            "not_a_feature",
            "Only numeric or categorical feature columns can become indicators",
            {"column": column.column_name},
        )
    indicator = Indicator(
        code=code,
        name=name,
        kind=column.dtype,
        dataset_id=dataset.id,
        column_name=column.column_name,
        owner_id=owner.id if owner else None,
        **fields,
    )
    db.add(indicator)
    db.flush()
    db.refresh(indicator)
    if dataset.target_column:
        save_scheme(db, indicator, "default", default_spec(indicator.kind), owner, True)
    return indicator


def find_column(dataset: Dataset, name: str) -> DatasetColumn:
    for column in dataset.columns:
        if name in (column.column_name, column.name):
            return column
    raise ApiError(400, "unknown_column", "Column not found in the dataset", {"column": name})


@router.get("", response_model=IndicatorPage)
def list_indicators(
    _: CurrentUser,
    db: Db,
    q: str | None = Query(None, max_length=64),
    category: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    dataset_id: uuid.UUID | None = None,
) -> IndicatorPage:
    query = select(Indicator)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                Indicator.code.like(like),
                func.lower(Indicator.name).like(like),
                func.lower(Indicator.name_en).like(like),
            )
        )
    if status_filter:
        query = query.where(Indicator.status == status_filter)
    if dataset_id:
        query = query.where(Indicator.dataset_id == dataset_id)
    sub = query.subquery()
    counts = dict(db.execute(select(sub.c.category, func.count()).group_by(sub.c.category)).all())
    if category:
        query = query.where(Indicator.category == category)
    items = db.scalars(query.order_by(Indicator.updated_at.desc())).unique().all()
    items = sorted(items, key=lambda i: -(i.default_scheme.iv if i.default_scheme else -1))
    return IndicatorPage(
        items=[IndicatorOut.model_validate(i) for i in items], total=len(items), counts=counts
    )


@router.post("", response_model=IndicatorDetail, status_code=status.HTTP_201_CREATED)
def create_indicator(body: IndicatorCreateIn, request: Request, user: CurrentUser, db: Db) -> Indicator:
    if db.scalar(select(Indicator.id).where(Indicator.code == body.code)):
        raise ApiError(409, "code_taken", "An indicator with this code already exists")
    dataset = get_dataset(db, body.dataset_id)
    column = find_column(dataset, body.column)
    fields = body.model_dump(exclude={"code", "name", "dataset_id", "column"})
    indicator = new_indicator(
        db, dataset, column, code=body.code, name=body.name.strip(), owner=user, **fields
    )
    audit.record(
        db,
        "indicator.created",
        actor=user,
        request=request,
        entity_type="indicator",
        entity_id=indicator.id,
        code=indicator.code,
    )
    db.commit()
    db.refresh(indicator)
    return indicator


@router.post("/import", response_model=list[IndicatorOut], status_code=status.HTTP_201_CREATED)
def import_indicators(
    body: IndicatorImportIn, request: Request, user: CurrentUser, db: Db
) -> list[Indicator]:
    dataset = get_dataset(db, body.dataset_id)
    taken = set(db.scalars(select(Indicator.code)).all())
    created = []
    for name in dict.fromkeys(body.columns):
        column = find_column(dataset, name)
        code = column.column_name if column.column_name[0].isalpha() else f"x_{column.column_name}"
        base, n = code, 2
        while code in taken:
            code, n = f"{base}_{n}", n + 1
        taken.add(code)
        created.append(
            new_indicator(
                db,
                dataset,
                column,
                code=code,
                name=column.name[:128],
                owner=user,
                category=body.category,
                status="draft",
            )
        )
    audit.record(
        db,
        "indicator.imported",
        actor=user,
        request=request,
        entity_type="dataset",
        entity_id=dataset.id,
        name=dataset.name,
        count=len(created),
    )
    db.commit()
    for indicator in created:
        db.refresh(indicator)
    return created


@router.get("/{indicator_id}", response_model=IndicatorDetail)
def get_one(indicator_id: uuid.UUID, _: CurrentUser, db: Db) -> Indicator:
    return get_indicator(db, indicator_id)


@router.patch("/{indicator_id}", response_model=IndicatorDetail)
def update_indicator(
    indicator_id: uuid.UUID, body: IndicatorUpdateIn, request: Request, user: CurrentUser, db: Db
) -> Indicator:
    indicator = get_indicator(db, indicator_id)
    changes = body.model_dump(exclude_unset=True, exclude={"clear_unit"})
    for key, value in changes.items():
        if value is not None:
            setattr(indicator, key, value.strip() if isinstance(value, str) and key != "status" else value)
    if body.clear_unit:
        indicator.unit = None
    audit.record(
        db,
        "indicator.updated",
        actor=user,
        request=request,
        entity_type="indicator",
        entity_id=indicator.id,
        code=indicator.code,
        fields=sorted(changes),
    )
    db.commit()
    db.refresh(indicator)
    return indicator


@router.delete("/{indicator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_indicator(indicator_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    indicator = get_indicator(db, indicator_id)
    ensure_owner(user, indicator.owner_id)
    indicator.default_scheme_id = None
    db.flush()
    db.delete(indicator)
    audit.record(
        db,
        "indicator.deleted",
        actor=user,
        request=request,
        entity_type="indicator",
        entity_id=indicator_id,
        code=indicator.code,
    )
    db.commit()


@router.post("/{indicator_id}/binning", response_model=BinningOut)
def preview_binning(indicator_id: uuid.UUID, spec: BinSpec, _: CurrentUser, db: Db) -> BinningOut:
    indicator = get_indicator(db, indicator_id)
    rule, result, notes = run_binning(db, indicator, spec)
    return BinningOut(**result, rule=rule.to_dict(), notes=notes)


@router.post("/{indicator_id}/schemes", response_model=SchemeOut, status_code=status.HTTP_201_CREATED)
def create_scheme(
    indicator_id: uuid.UUID, body: SchemeCreateIn, request: Request, user: CurrentUser, db: Db
) -> BinningScheme:
    indicator = get_indicator(db, indicator_id)
    scheme = save_scheme(db, indicator, body.name.strip(), body.spec, user, body.make_default)
    audit.record(
        db,
        "scheme.created",
        actor=user,
        request=request,
        entity_type="indicator",
        entity_id=indicator.id,
        code=indicator.code,
        scheme=scheme.name,
        iv=scheme.iv,
    )
    db.commit()
    db.refresh(scheme)
    return scheme


@router.post("/{indicator_id}/schemes/{scheme_id}/default", response_model=IndicatorDetail)
def make_default(
    indicator_id: uuid.UUID, scheme_id: uuid.UUID, request: Request, user: CurrentUser, db: Db
) -> Indicator:
    indicator = get_indicator(db, indicator_id)
    scheme = db.get(BinningScheme, scheme_id)
    if scheme is None or scheme.indicator_id != indicator.id:
        raise ApiError(404, "scheme_not_found", "Binning scheme not found")
    indicator.default_scheme_id = scheme.id
    audit.record(
        db,
        "scheme.default",
        actor=user,
        request=request,
        entity_type="indicator",
        entity_id=indicator.id,
        code=indicator.code,
        scheme=scheme.name,
    )
    db.commit()
    db.refresh(indicator)
    return indicator


@router.delete("/{indicator_id}/schemes/{scheme_id}", response_model=IndicatorDetail)
def delete_scheme(
    indicator_id: uuid.UUID, scheme_id: uuid.UUID, request: Request, user: CurrentUser, db: Db
) -> Indicator:
    indicator = get_indicator(db, indicator_id)
    scheme = db.get(BinningScheme, scheme_id)
    if scheme is None or scheme.indicator_id != indicator.id:
        raise ApiError(404, "scheme_not_found", "Binning scheme not found")
    if indicator.default_scheme_id == scheme.id:
        others = [s for s in indicator.schemes if s.id != scheme.id]
        indicator.default_scheme_id = others[0].id if others else None
        db.flush()
    db.delete(scheme)
    audit.record(
        db,
        "scheme.deleted",
        actor=user,
        request=request,
        entity_type="indicator",
        entity_id=indicator.id,
        code=indicator.code,
        scheme=scheme.name,
    )
    db.commit()
    db.refresh(indicator)
    return indicator


@router.get("/{indicator_id}/stability", response_model=StabilityOut)
def stability(
    indicator_id: uuid.UUID,
    _: CurrentUser,
    db: Db,
    scheme_id: uuid.UUID | None = None,
    reference_months: int | None = Query(None, ge=1, le=60),
) -> StabilityOut:
    """Monthly PSI of a saved scheme against the first months of the source dataset."""
    indicator = get_indicator(db, indicator_id)
    scheme = db.get(BinningScheme, scheme_id) if scheme_id else indicator.default_scheme
    if scheme is None or scheme.indicator_id != indicator.id:
        raise ApiError(404, "scheme_not_found", "Binning scheme not found")
    dataset = source(db, indicator)
    if not dataset.date_column:
        raise ApiError(400, "no_date_column", "Set the date column of the source dataset to see stability")
    columns = [indicator.column_name, dataset.date_column]
    if dataset.target_column:
        columns.append(dataset.target_column)
    frame = store.read_columns(db, dataset, columns)
    months = pd.to_datetime(frame[dataset.date_column], errors="coerce").dt.to_period("M").astype("string")
    frame = frame.assign(_month=months).dropna(subset=["_month"])
    y = store.labels(dataset, frame) if dataset.target_column else pd.Series(index=frame.index, dtype=float)
    rule = binning.Rule.from_dict(scheme.rule)
    groups = rule.assign(frame[indicator.column_name])
    ordered = sorted(frame["_month"].unique())
    if len(ordered) < 2:
        raise ApiError(400, "too_few_months", "The dataset covers fewer than two months")
    n_ref = min(reference_months or max(1, len(ordered) // 2), len(ordered) - 1)
    reference = set(ordered[:n_ref])
    in_ref = frame["_month"].isin(reference)
    result = []
    for month in ordered:
        part = frame["_month"] == month
        shares = groups[part].value_counts(normalize=True)
        value = binning.psi_table_value(groups[in_ref], groups[part])
        bad = y[part].dropna()
        result.append(
            StabilityMonth(
                month=month,
                rows=int(part.sum()),
                psi=round(value, 6),
                bad_rate=round(float(bad.mean()), 6) if len(bad) else None,
                in_reference=month in reference,
                shares={str(k): round(float(v), 6) for k, v in shares.items()},
            )
        )
    bins = [{"code": b["code"], **rule.describe(b["code"])} for b in scheme.bins]
    return StabilityOut(
        scheme_id=scheme.id, reference=[ordered[0], ordered[n_ref - 1]], months=result, bins=bins
    )
