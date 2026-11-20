"""Database engine, session factory and declarative base."""

from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    type_annotation_map = {
        dict[str, Any]: JSONB,
        datetime: DateTime(timezone=True),
    }


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session
