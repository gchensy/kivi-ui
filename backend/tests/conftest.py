import os

os.environ["KIVI_ENV"] = "test"
os.environ.setdefault("KIVI_DATABASE_URL", "postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from kivi_ui.config import get_settings  # noqa: E402
from kivi_ui.db import Base, get_engine, get_sessionmaker  # noqa: E402
from kivi_ui.main import create_app  # noqa: E402
from kivi_ui.models import Role, User, UserStatus  # noqa: E402
from kivi_ui.security import hash_password  # noqa: E402

PASSWORD = "Passw0rd-test"


@pytest.fixture(scope="session", autouse=True)
def schema():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean(schema):
    yield
    with get_engine().begin() as connection:
        connection.execute(text("TRUNCATE audit_logs, analytics_snapshots, users CASCADE"))
    get_settings.cache_clear()


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
