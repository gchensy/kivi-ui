"""Background handlers: train a model version, score a dataset with a version."""

import uuid
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics.binning import BinningError
from .analytics.training import Candidate, TrainConfig, TrainingError, score_frame, train
from .data import store
from .jobs import JobFailed, handler, on_failure
from .models import Dataset, Indicator, Job, ModelVersion, User
from .routes.indicators import default_spec


def _version(db: Session, job: Job) -> ModelVersion:
    version = db.get(ModelVersion, uuid.UUID(job.params["version_id"]))
    if version is None:
        raise JobFailed("The model version was deleted")
    return version


@handler("train_model")
def train_model(db: Session, job: Job) -> dict[str, Any]:
    version = _version(db, job)
    dataset = version.dataset
    if dataset is None:
        raise JobFailed("The training dataset was deleted")
    ids = [uuid.UUID(i) for i in version.config["indicator_ids"]]
    indicators = db.scalars(select(Indicator).where(Indicator.id.in_(ids))).unique().all()
    headers = {c.column_name: c.name for c in dataset.columns}
    candidates = []
    for indicator in indicators:
        scheme = indicator.default_scheme
        spec = scheme.spec if scheme else default_spec(indicator.kind).model_dump()
        candidates.append(
            Candidate(
                str(indicator.id),
                indicator.code,
                indicator.name,
                indicator.name_en,
                indicator.column_name,
                indicator.kind,
                indicator.unit,
                spec,
                headers.get(indicator.column_name),
            )
        )
    if not candidates:
        raise JobFailed("indicators_missing: none of the chosen indicators exist any more")
    try:
        columns = [c.column for c in candidates] + [dataset.target_column or ""]
        if dataset.date_column:
            columns.append(dataset.date_column)
        frame = store.read_columns(db, dataset, list(dict.fromkeys(columns)))
        y = store.labels(dataset, frame)
        keep = y.notna()
        frame, y = frame[keep].reset_index(drop=True), y[keep].astype(int).reset_index(drop=True)
        dates = frame[dataset.date_column] if dataset.date_column else None
        result = train(frame, y, dates, candidates, TrainConfig(**version.config["train"]))
    except (TrainingError, BinningError, store.DataError) as error:
        raise JobFailed(f"{error.code}: {error}") from error
    version.result = result
    version.status = "draft"
    version.error = None
    version.feature_count = len(result["features"])
    for split in ("train", "test", "oot"):
        roc = result["evaluation"].get(split, {}).get("roc") or {}
        setattr(version, f"auc_{split}", roc.get("auc"))
        setattr(version, f"ks_{split}", roc.get("ks"))
    return {"version_id": str(version.id), "features": version.feature_count}


@on_failure("train_model")
def train_failed(db: Session, job: Job) -> None:
    version = db.get(ModelVersion, uuid.UUID(job.params["version_id"]))
    if version is not None:
        version.status, version.error = "failed", job.error


@handler("score_dataset")
def score_dataset(db: Session, job: Job) -> dict[str, Any]:
    from .routes.datasets import create_dataset

    version = _version(db, job)
    source = db.get(Dataset, uuid.UUID(job.params["dataset_id"]))
    if source is None:
        raise JobFailed("The dataset to score was deleted")
    features = version.result.get("features", [])
    # Match each variable by its uploaded header (SQL names of non-ASCII headers are positional),
    # falling back to the SQL name for versions trained before headers were recorded.
    by_header = {c.name: c.column_name for c in source.columns}
    by_name = {c.column_name for c in source.columns}
    mapping, missing = {}, []
    for f in features:
        header = f.get("header")
        found = by_header.get(header) if header else (f["column"] if f["column"] in by_name else None)
        if found is None:
            missing.append(header or f["column"])
        else:
            mapping[f["column"]] = found
    if missing:
        raise JobFailed(f"missing_columns: the dataset lacks {', '.join(missing)}")
    keys = [c for c in (source.id_column, source.date_column, source.target_column) if c]
    frame = store.read_columns(db, source, list(dict.fromkeys(keys + list(mapping.values()))))
    features_frame = pd.DataFrame(
        {column: frame[found] for column, found in mapping.items()}, index=frame.index
    )
    scored = score_frame(version.result, features_frame)
    headers = {c.column_name: c.name for c in source.columns}
    output = pd.concat([frame[keys].rename(columns=headers), scored], axis=1)
    names = store.sanitize([str(c) for c in output.columns])  # positional: c3 for a Chinese header
    owner = db.get(User, job.created_by) if job.created_by else None
    model = version.model
    dataset = create_dataset(
        db,
        output,
        name=f"{model.code} v{version.version} · {source.name}"[:128],
        description=f"Scores from {model.name} v{version.version} on {source.name}.",
        owner=owner,
        source="score",
        roles={
            "target_column": names[keys.index(source.target_column)] if source.target_column else None,
            "target_event": source.target_event,
        },
        dtypes={headers[source.id_column]: "text"} if source.id_column else None,
    )
    return {"dataset_id": str(dataset.id), "rows": dataset.row_count}
