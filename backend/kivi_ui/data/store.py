"""Physical storage of sample data in the ``kivi_data`` schema, plus profiling."""

import csv
import io
import re
import uuid
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from ..analytics.binning import BinningError, BinSpec, fit, iv_level, report
from ..models import Dataset

SCHEMA = "kivi_data"
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 500_000
MAX_COLUMNS = 300
TARGET_NAMES = ("target", "label", "y", "bad", "is_bad", "default", "flag", "bad_flag", "default_flag")
TARGET_HEADERS = ("目标", "标签", "是否违约", "是否逾期", "违约标记", "坏样本", "坏样本标记")
EVENT_VALUES = ("1", "1.0", "yes", "y", "true", "bad", "default", "是", "坏")
DATE_HINT = re.compile(r"(date|time|month|dt|_at|日期|时间)$", re.I)


class DataError(ValueError):
    def __init__(self, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.code, self.detail = code, detail


# ---- Reading uploads ------------------------------------------------------------------------


def decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DataError("bad_encoding", "The file is neither UTF-8 nor GBK text")


def read_csv(content: bytes) -> pd.DataFrame:
    if len(content) > MAX_BYTES:
        raise DataError("file_too_large", "The file is larger than 20 MB", limit_mb=MAX_BYTES // 2**20)
    body = decode(content)
    if not body.strip():
        raise DataError("empty_file", "The file is empty")
    try:
        delimiter = csv.Sniffer().sniff(body[:65536], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    try:
        frame = pd.read_csv(io.StringIO(body), sep=delimiter, low_memory=False)
    except (pd.errors.ParserError, ValueError) as error:
        raise DataError("bad_csv", f"Could not parse the CSV: {error}") from error
    if frame.shape[1] < 2:
        raise DataError("too_few_columns", "The file needs at least two columns")
    if frame.shape[1] > MAX_COLUMNS:
        raise DataError("too_many_columns", "Too many columns", limit=MAX_COLUMNS)
    if len(frame) > MAX_ROWS:
        raise DataError("too_many_rows", "Too many rows", limit=MAX_ROWS)
    if frame.empty:
        raise DataError("empty_file", "The file has a header but no rows")
    return frame


def sanitize(names: list[str]) -> list[str]:
    """SQL-safe, unique, lowercase column names (original headers are kept separately)."""
    out, seen = [], set()
    for i, name in enumerate(names):
        base = re.sub(r"[^0-9a-zA-Z_]+", "_", str(name).strip()).strip("_").lower()[:55]
        if not base or base[0].isdigit():
            base = f"c{i + 1}_{base}".rstrip("_")
        candidate, n = base, 2
        while candidate in seen:
            candidate, n = f"{base}_{n}", n + 1
        seen.add(candidate)
        out.append(candidate)
    return out


def infer_dtype(series: pd.Series, name: str) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "category"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    observed = series.dropna().astype(str)
    if observed.empty:
        return "text"
    numeric = pd.to_numeric(observed, errors="coerce")
    if numeric.notna().mean() >= 0.98:
        return "numeric"
    has_digits = observed.str.contains(r"\d").mean() > 0.95
    if has_digits and (
        DATE_HINT.search(name) or observed.str.match(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?").mean() > 0.9
    ):
        parsed = pd.to_datetime(observed, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.95:
            return "datetime"
    unique = observed.nunique()
    if unique <= 60 or unique <= 0.05 * len(observed):
        return "category"
    return "text"


def normalise(
    frame: pd.DataFrame, dtypes: dict[str, str] | None = None
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Rename to SQL names and coerce each column to its inferred (or given) type."""
    headers = [str(c) for c in frame.columns]
    names = sanitize(headers)
    out = pd.DataFrame(index=frame.index)
    meta = []
    for position, (header, name) in enumerate(zip(headers, names, strict=True)):
        series = frame.iloc[:, position]
        dtype = (dtypes or {}).get(header) or infer_dtype(series, header)
        if dtype == "numeric":
            series = pd.to_numeric(series, errors="coerce")
        elif dtype == "datetime":
            series = pd.to_datetime(series, errors="coerce", format="mixed")
        else:
            series = series.astype("string")
        out[name] = series
        meta.append({"position": position, "name": header, "column_name": name, "dtype": dtype})
    return out, meta


def guess_roles(frame: pd.DataFrame, meta: list[dict[str, Any]]) -> dict[str, str | None]:
    """Pick likely target, event value, date and id columns."""
    target = event = date = ident = None
    by_name = {m["column_name"]: m for m in meta}
    by_header = {m["name"].strip(): m["column_name"] for m in meta}
    candidates = [*TARGET_NAMES, *(by_header[h] for h in TARGET_HEADERS if h in by_header)]
    for candidate in candidates:  # in priority order: "target" beats "default"
        if candidate in by_name:
            try:
                event = validate_target(frame, candidate, None)
            except DataError:
                continue
            target = candidate
            break
    for m in meta:
        col = frame[m["column_name"]]
        values = col.dropna()
        if date is None and m["dtype"] == "datetime":
            date = m["column_name"]
        if (
            ident is None
            and m["dtype"] in ("text", "numeric")
            and values.nunique() == len(frame)
            and len(frame) > 20
        ):
            if m["dtype"] == "text" or re.search(r"(^id$|_id$|^uuid$|编号)", m["name"], re.I):
                ident = m["column_name"]
    return {"target_column": target, "target_event": event, "date_column": date, "id_column": ident}


def guess_event(values: pd.Series) -> str | None:
    levels = [str(v) for v in values.dropna().unique()]
    if len(levels) != 2:
        return None
    lowered = {level.lower(): level for level in levels}
    for candidate in EVENT_VALUES:
        if candidate in lowered:
            return lowered[candidate]
    return None


# ---- Database tables ------------------------------------------------------------------------


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))


def new_table_name() -> str:
    return f"ds_{uuid.uuid4().hex[:16]}"


def write_table(engine: Engine, table: str, frame: pd.DataFrame) -> None:
    """Create the table from the frame's types, then bulk-load it with COPY."""
    ensure_schema(engine)
    frame.head(0).to_sql(table, engine, schema=SCHEMA, index=False, if_exists="fail")
    columns = ", ".join(_quote(c) for c in frame.columns)
    values = frame.astype(object).where(frame.notna(), None)
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            with cursor.copy(f"COPY {SCHEMA}.{_quote(table)} ({columns}) FROM STDIN") as copy:
                for row in values.itertuples(index=False, name=None):
                    copy.write_row(row)
        raw.commit()
    finally:
        raw.close()


def drop_table(engine: Engine, table: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f'DROP TABLE IF EXISTS {SCHEMA}."{table}"'))


def _quote(name: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise DataError("bad_column", "Invalid column name", column=name)
    return f'"{name}"'


def read_columns(db: Session, dataset: Dataset, columns: list[str]) -> pd.DataFrame:
    known = {c.column_name for c in dataset.columns}
    unknown = [c for c in columns if c not in known]
    if unknown:
        raise DataError("unknown_column", "Column not found in the dataset", columns=unknown)
    selected = ", ".join(_quote(c) for c in dict.fromkeys(columns))
    sql = f"SELECT {selected} FROM {SCHEMA}.{_quote(dataset.table_name)}"
    return pd.read_sql_query(text(sql), db.connection())


def preview(db: Session, dataset: Dataset, limit: int, offset: int) -> list[list[Any]]:
    names = [c.column_name for c in dataset.columns]
    table = f"{SCHEMA}.{_quote(dataset.table_name)}"
    sql = (
        f"SELECT {', '.join(_quote(c) for c in names)} FROM {table} ORDER BY ctid LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(text(sql), {"limit": limit, "offset": offset}).all()
    return [[_jsonable(v) for v in row] for row in rows]


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        return None if not np.isfinite(value) else value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


# ---- Labels and profiling -------------------------------------------------------------------


def labels(dataset: Dataset, frame: pd.DataFrame) -> pd.Series:
    """0/1 target aligned with `frame`; rows with a missing label are NaN."""
    if not dataset.target_column:
        raise DataError("no_target", "Choose the target column of this dataset first")
    raw = frame[dataset.target_column]
    if dataset.target_event is not None:
        y = (raw.astype("string") == dataset.target_event).astype(float)
    else:
        y = pd.to_numeric(raw, errors="coerce")
    return y.where(raw.notna())


def validate_target(frame: pd.DataFrame, column: str, event: str | None) -> str | None:
    values = frame[column].dropna()
    levels = {str(v) for v in values.unique()}
    if len(levels) != 2:
        raise DataError(
            "target_not_binary",
            "The target must have exactly two distinct values",
            values=sorted(levels)[:10],
        )
    numeric = pd.to_numeric(values, errors="coerce")
    if event is None and numeric.notna().all() and set(numeric.unique()) <= {0, 1}:
        return None
    if event is None:
        event = guess_event(values)
    if event is None or event not in levels:
        raise DataError(
            "target_event_required", "Choose which target value marks a bad outcome", values=sorted(levels)
        )
    return event


def _stats(series: pd.Series, dtype: str) -> dict[str, Any]:
    observed = series.dropna()
    if observed.empty:
        return {}
    if dtype == "numeric":
        q = observed.quantile([0.25, 0.5, 0.75])
        return {
            k: _jsonable(float(v))
            for k, v in {
                "min": observed.min(),
                "max": observed.max(),
                "mean": observed.mean(),
                "std": observed.std(),
                "p25": q.iloc[0],
                "p50": q.iloc[1],
                "p75": q.iloc[2],
            }.items()
        }
    if dtype == "datetime":
        return {"min": observed.min().isoformat(), "max": observed.max().isoformat()}
    top = observed.astype(str).value_counts(normalize=True).head(5)
    return {"top": [{"value": k, "share": round(float(v), 4)} for k, v in top.items()]}


def quick_spec(series: pd.Series, dtype: str, base: BinSpec) -> BinSpec:
    """Category grouping for categories; one bin per value for numeric columns with few values."""
    if dtype == "category":
        return base.model_copy(update={"method": "category"})
    values = np.sort(pd.to_numeric(series, errors="coerce").dropna().unique())
    if 1 < len(values) <= 10 and base.method in ("quantile", "uniform"):
        return base.model_copy(update={"method": "manual", "cuts": list((values[:-1] + values[1:]) / 2)})
    return base


def profile(db: Session, dataset: Dataset) -> None:
    """Recompute column statistics, quick IV (kivi, 5 quantile bins) and monthly totals."""
    frame = read_columns(db, dataset, [c.column_name for c in dataset.columns])
    y = labels(dataset, frame) if dataset.target_column else None
    labelled = y.notna() if y is not None else None
    dataset.row_count = len(frame)
    dataset.column_count = len(dataset.columns)
    dataset.bad_rate = float(y.mean()) if y is not None and labelled.any() else None
    for column in dataset.columns:
        series = frame[column.column_name]
        column.missing_rate = float(series.isna().mean())
        column.unique_count = int(series.nunique())
        column.stats = _stats(series, column.dtype)
        column.iv = None
        if column.role != "feature" or y is None or column.dtype not in ("numeric", "category"):
            continue
        try:
            values, target = series[labelled], y[labelled].astype(int)
            spec = quick_spec(values, column.dtype, BinSpec(method="quantile", bins=5, min_bin_share=0.02))
            rule, _ = fit(values, target, spec, column.dtype)
            column.iv = report(rule, values, target)["iv"]
        except (BinningError, ValueError):
            column.iv = None
    monthly: list[dict[str, Any]] = []
    if dataset.date_column:
        dates = pd.to_datetime(frame[dataset.date_column], errors="coerce")
        months = dates.dt.to_period("M").astype("string")
        grouped = pd.DataFrame({"month": months, "y": y if y is not None else np.nan}).dropna(
            subset=["month"]
        )
        for month, part in grouped.groupby("month", sort=True):
            bad = part.y.dropna()
            monthly.append(
                {
                    "month": str(month),
                    "rows": int(len(part)),
                    "bad_rate": _jsonable(float(bad.mean())) if len(bad) else None,
                }
            )
        dataset.profile = {"monthly": monthly, "date_range": [_jsonable(dates.min()), _jsonable(dates.max())]}
    else:
        dataset.profile = {"monthly": [], "date_range": None}


def screening(db: Session, dataset: Dataset, spec: BinSpec) -> list[dict[str, Any]]:
    """Bin every feature with one spec and rank by IV."""
    if not dataset.target_column:
        raise DataError("no_target", "Choose the target column of this dataset first")
    features = [c for c in dataset.columns if c.role == "feature" and c.dtype in ("numeric", "category")]
    frame = read_columns(db, dataset, [c.column_name for c in features] + [dataset.target_column])
    y = labels(dataset, frame)
    labelled = y.notna()
    results = []
    for column in features:
        values, target = frame[column.column_name][labelled], y[labelled].astype(int)
        method_spec = quick_spec(values, column.dtype, spec)
        try:
            rule, notes = fit(values, target, method_spec, column.dtype)
            r = report(rule, values, target)
            results.append(
                {
                    "column": column.column_name,
                    "name": column.name,
                    "dtype": column.dtype,
                    "iv": r["iv"],
                    "level": r["level"],
                    "trend": r["trend"],
                    "bins": len(r["bins"]),
                    "missing_rate": r["missing_rate"],
                    "note": notes[0] if notes else None,
                }
            )
        except BinningError as error:
            results.append(
                {
                    "column": column.column_name,
                    "name": column.name,
                    "dtype": column.dtype,
                    "iv": None,
                    "level": None,
                    "trend": None,
                    "bins": 0,
                    "missing_rate": float(values.isna().mean()),
                    "note": str(error),
                }
            )
    results.sort(key=lambda r: -(r["iv"] or -1))
    return results


def iv_level_or_none(iv: float | None) -> str | None:
    return iv_level(iv) if iv is not None else None
