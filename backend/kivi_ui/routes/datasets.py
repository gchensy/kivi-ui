"""Sample datasets: upload, profile, preview and IV screening."""

import uuid

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status
from sqlalchemy import func, select

from .. import audit
from ..analytics.binning import BinSpec
from ..data import store
from ..data_schemas import DatasetDetail, DatasetOut, DatasetUpdateIn, PreviewOut, ScreeningRow
from ..db import get_engine
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..models import Dataset, DatasetColumn, Indicator, Role, User

router = APIRouter(prefix="/datasets", tags=["datasets"])


def get_dataset(db: Db, dataset_id: uuid.UUID) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    return dataset


def ensure_owner(user: User, owner_id: uuid.UUID | None) -> None:
    if user.role is not Role.admin and owner_id != user.id:
        raise ApiError(403, "forbidden", "Only the owner or an administrator can do this")


def detail(db: Db, dataset: Dataset) -> DatasetDetail:
    count = db.scalar(select(func.count()).where(Indicator.dataset_id == dataset.id)) or 0
    return DatasetDetail.model_validate(dataset).model_copy(update={"indicator_count": count})


def create_dataset(
    db, frame, *, name, description, owner, source="upload", file_name=None, roles=None, dtypes=None
):
    """Store a raw frame as a new dataset table, guess roles and profile it."""
    data, meta = store.normalise(frame, dtypes)
    guessed = store.guess_roles(data, meta)
    if roles:
        guessed.update(roles)
    table = store.new_table_name()
    try:
        store.write_table(get_engine(), table, data)
        dataset = Dataset(
            name=name,
            description=description,
            source=source,
            file_name=file_name,
            table_name=table,
            owner_id=owner.id if owner else None,
            **guessed,
        )
        special = {
            guessed["target_column"]: "target",
            guessed["date_column"]: "date",
            guessed["id_column"]: "id",
        }
        for m in meta:
            role = special.get(m["column_name"]) or (
                "feature" if m["dtype"] in ("numeric", "category") else "ignore"
            )
            dataset.columns.append(DatasetColumn(role=role, **m))
        db.add(dataset)
        db.flush()
        store.profile(db, dataset)
        return dataset
    except Exception:
        db.rollback()
        store.drop_table(get_engine(), table)
        raise


@router.get("", response_model=list[DatasetOut])
def list_datasets(_: CurrentUser, db: Db) -> list[Dataset]:
    return list(db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).unique().all())


@router.post("", response_model=DatasetDetail, status_code=status.HTTP_201_CREATED)
def upload_dataset(
    request: Request,
    user: CurrentUser,
    db: Db,
    file: UploadFile = File(...),
    name: str = Form("", max_length=128),
    description: str = Form("", max_length=1000),
) -> DatasetDetail:
    content = file.file.read(store.MAX_BYTES + 1)
    frame = store.read_csv(content)
    title = name.strip() or (file.filename or "dataset").rsplit(".", 1)[0][:128]
    dataset = create_dataset(
        db, frame, name=title, description=description.strip(), owner=user, file_name=file.filename
    )
    audit.record(
        db,
        "dataset.created",
        actor=user,
        request=request,
        entity_type="dataset",
        entity_id=dataset.id,
        name=dataset.name,
        rows=dataset.row_count,
    )
    db.commit()
    return detail(db, dataset)


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_one(dataset_id: uuid.UUID, _: CurrentUser, db: Db) -> DatasetDetail:
    return detail(db, get_dataset(db, dataset_id))


@router.patch("/{dataset_id}", response_model=DatasetDetail)
def update_dataset(
    dataset_id: uuid.UUID, body: DatasetUpdateIn, request: Request, user: CurrentUser, db: Db
) -> DatasetDetail:
    dataset = get_dataset(db, dataset_id)
    ensure_owner(user, dataset.owner_id)
    columns = {c.column_name: c for c in dataset.columns}
    changes = body.model_dump(exclude_unset=True)
    reprofile = False

    def column(name: str) -> DatasetColumn:
        if name not in columns:
            raise ApiError(400, "unknown_column", "Column not found in the dataset", {"column": name})
        return columns[name]

    special_columns = {dataset.target_column, dataset.date_column, dataset.id_column}
    for key, value in (body.roles or {}).items():
        target = column(key)
        if key in special_columns:
            raise ApiError(
                400, "invalid_role", "Clear the target, date or id column before changing its role"
            )
        if value in ("target", "date", "id"):
            raise ApiError(400, "invalid_role", "Set target, date and id with their own fields")
        if target.role != value:
            target.role, reprofile = value, True

    for field in body.clear:
        current = getattr(dataset, field)
        if current:
            columns[current].role = "ignore" if columns[current].dtype in ("datetime", "text") else "feature"
            setattr(dataset, field, None)
            if field == "target_column":
                dataset.target_event = None
            reprofile = True

    if body.target_column is not None:
        col = column(body.target_column)
        frame = store.read_columns(db, dataset, [col.column_name])
        event = store.validate_target(frame, col.column_name, body.target_event)
        if dataset.target_column and dataset.target_column != col.column_name:
            columns[dataset.target_column].role = "feature"
        dataset.target_column, dataset.target_event, col.role = col.column_name, event, "target"
        reprofile = True
    if body.date_column is not None:
        col = column(body.date_column)
        if col.dtype != "datetime":
            raise ApiError(400, "not_a_date", "The date column must contain dates")
        if dataset.date_column and dataset.date_column != col.column_name:
            columns[dataset.date_column].role = "ignore"
        dataset.date_column, col.role = col.column_name, "date"
        reprofile = True
    if body.id_column is not None:
        col = column(body.id_column)
        if dataset.id_column and dataset.id_column != col.column_name:
            columns[dataset.id_column].role = "ignore"
        dataset.id_column, col.role = col.column_name, "id"
    if body.name is not None:
        dataset.name = body.name.strip()
    if body.description is not None:
        dataset.description = body.description.strip()

    if reprofile:
        store.profile(db, dataset)
    audit.record(
        db,
        "dataset.updated",
        actor=user,
        request=request,
        entity_type="dataset",
        entity_id=dataset.id,
        name=dataset.name,
        fields=sorted(changes),
    )
    db.commit()
    return detail(db, dataset)


@router.get("/{dataset_id}/preview", response_model=PreviewOut)
def preview(
    dataset_id: uuid.UUID,
    _: CurrentUser,
    db: Db,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PreviewOut:
    dataset = get_dataset(db, dataset_id)
    return PreviewOut(
        columns=[c.name for c in dataset.columns],
        rows=store.preview(db, dataset, limit, offset),
        total=dataset.row_count,
    )


@router.post("/{dataset_id}/screening", response_model=list[ScreeningRow])
def screen(dataset_id: uuid.UUID, spec: BinSpec, _: CurrentUser, db: Db) -> list[ScreeningRow]:
    dataset = get_dataset(db, dataset_id)
    rows = store.screening(db, dataset, spec)
    existing = dict(
        db.execute(
            select(Indicator.column_name, Indicator.id).where(Indicator.dataset_id == dataset.id)
        ).all()
    )
    return [ScreeningRow(**row, indicator_id=existing.get(row["column"])) for row in rows]


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    dataset = get_dataset(db, dataset_id)
    ensure_owner(user, dataset.owner_id)
    table, name = dataset.table_name, dataset.name
    db.delete(dataset)
    audit.record(
        db,
        "dataset.deleted",
        actor=user,
        request=request,
        entity_type="dataset",
        entity_id=dataset_id,
        name=name,
    )
    db.commit()
    store.drop_table(get_engine(), table)
