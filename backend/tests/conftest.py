import os

os.environ["KIVI_ENV"] = "test"
os.environ["KIVI_RUN_WORKER"] = "false"
os.environ.setdefault("KIVI_DATABASE_URL", "postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi_test")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from kivi_ui.config import get_settings  # noqa: E402
from kivi_ui.data.store import SCHEMA as DATA_SCHEMA  # noqa: E402
from kivi_ui.db import Base, get_engine, get_sessionmaker  # noqa: E402
from kivi_ui.main import create_app  # noqa: E402
from kivi_ui.models import Role, User, UserStatus  # noqa: E402
from kivi_ui.rules import runtime  # noqa: E402
from kivi_ui.security import hash_password  # noqa: E402

PASSWORD = "Passw0rd-test"
# CASCADE also covers the indicators <-> binning_schemes foreign key cycle.
TABLES = (
    "alerts, monitor_runs, monitors, decision_logs, api_tokens, risk_list_items, risk_lists,"
    " strategy_reviews, strategy_versions, strategies, model_reviews, model_versions, risk_models, jobs,"
    " binning_schemes, indicators, dataset_columns, datasets, audit_logs, users"
)


def reset_data_schema(connection) -> None:
    """Drop every uploaded dataset table (they live outside the ORM metadata)."""
    connection.execute(text(f"DROP SCHEMA IF EXISTS {DATA_SCHEMA} CASCADE"))
    connection.execute(text(f"CREATE SCHEMA {DATA_SCHEMA}"))


@pytest.fixture(scope="session", autouse=True)
def schema():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        reset_data_schema(connection)
    yield
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {DATA_SCHEMA} CASCADE"))


@pytest.fixture(autouse=True)
def clean(schema):
    yield
    with get_engine().begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        reset_data_schema(connection)
    get_settings.cache_clear()
    runtime.invalidate()  # the decision API caches online strategies for 30 seconds


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def make_user(db):
    def make(username, role=Role.analyst, status=UserStatus.active, password=PASSWORD):
        user = User(
            username=username,
            email=f"{username}@example.com",
            display_name=username,
            role=role,
            status=status,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()
        return user

    return make


def client() -> TestClient:
    return TestClient(create_app(), headers={"X-Requested-With": "pytest"})


@pytest.fixture
def anon():
    return client()


@pytest.fixture
def login():
    def sign_in(username, password=PASSWORD):
        c = client()
        response = c.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.json()
        return c

    return sign_in


# ---- Sample data for the dataset and indicator APIs ---------------------------------------------

MONTHS = 6


def loan_frame(rows: int = 240, seed: int = 3) -> pd.DataFrame:
    """Six monthly cohorts of loans: a 0/1 target, an apply date, numeric and categorical
    features with missing values, two binary text columns, and income drifting upwards
    in the last two months."""
    rng = np.random.default_rng(seed)
    risk = rng.normal(size=rows)
    month = np.arange(rows) * MONTHS // rows
    day = rng.integers(1, 29, rows)
    target = (rng.random(rows) < 1 / (1 + np.exp(1.2 - 1.5 * risk))).astype(int)
    income = np.round(9000 - 2500 * risk + rng.normal(0, 600, rows) + np.where(month >= 4, 8000, 0), -1)
    income[::17] = np.nan
    city = np.where(risk > 0.6, "east", np.where(risk < -0.6, "north", "south")).astype(object)
    city[5::23] = None
    return pd.DataFrame(
        {
            "id": np.arange(1, rows + 1),
            "apply_date": [f"2026-{m + 1:02d}-{d:02d}" for m, d in zip(month, day, strict=True)],
            "income": income,
            "city": city,
            "target": target,
            "outcome": np.where(risk + rng.normal(0, 0.8, rows) > 0.9, "overdue", "paid"),
            "responded": rng.choice(["yes", "no"], rows),
            "年龄": np.clip(np.round(38 - 5 * risk + rng.normal(0, 6, rows)), 20, 65).astype(int),
        }
    )


def loan_csv(**kwargs) -> bytes:
    return loan_frame(**kwargs).to_csv(index=False).encode()


def upload(c: TestClient, content: bytes | None = None, *, name: str = "loans", filename: str = "loans.csv"):
    content = loan_csv() if content is None else content
    return c.post("/api/v1/datasets", files={"file": (filename, content, "text/csv")}, data={"name": name})
