"""Load what a strategy needs to run: online models, watchlist digests, a hasher.

The decision API caches the online strategy for a short time so each request
is a single in-memory evaluation; lifecycle changes invalidate the cache.
"""

import threading
import time
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ModelVersion, RiskList, RiskListItem, RiskModel, Strategy, StrategyVersion
from .dsl import Definition, references
from .engine import Context, Hasher, ModelRuntime, make_hasher

TTL_SECONDS = 30
_lock = threading.Lock()
_strategies: dict[str, tuple[float, tuple]] = {}


@lru_cache
def _hasher_for(key: str) -> Hasher:
    return make_hasher(key)


def hasher() -> Hasher:
    settings = get_settings()
    return _hasher_for(settings.list_key or settings.secret_key)


def load_lists(db: Session, codes: set[str]) -> dict[str, frozenset[str]]:
    if not codes:
        return {}
    now = datetime.now(UTC)
    lists = {code: set() for code in db.scalars(select(RiskList.code).where(RiskList.code.in_(codes)))}
    rows = db.execute(
        select(RiskList.code, RiskListItem.value_hash)
        .join(RiskListItem, RiskListItem.list_id == RiskList.id)
        .where(
            RiskList.code.in_(codes), or_(RiskListItem.expires_at.is_(None), RiskListItem.expires_at > now)
        )
    ).all()
    for code, digest in rows:
        lists[code].add(digest)
    return {code: frozenset(values) for code, values in lists.items()}


def load_models(db: Session, codes: set[str]) -> dict[str, ModelRuntime]:
    if not codes:
        return {}
    rows = db.execute(
        select(RiskModel.code, ModelVersion)
        .join(ModelVersion, ModelVersion.model_id == RiskModel.id)
        .where(RiskModel.code.in_(codes), ModelVersion.status == "online")
    ).all()
    return {code: ModelRuntime(code, str(v.id), v.version, v.result) for code, v in rows}


def context_for(db: Session, definition: Definition) -> Context:
    refs = references(definition)
    return Context(
        models=load_models(db, refs["models"]), lists=load_lists(db, refs["lists"]), hasher=hasher()
    )


def online_strategies_using(db: Session, kind: str, code: str) -> list[str]:
    """Codes of strategies whose online version references watchlist or model `code` (kind lists|models)."""
    rows = db.execute(
        select(Strategy.code, StrategyVersion.definition)
        .join(StrategyVersion, StrategyVersion.strategy_id == Strategy.id)
        .where(StrategyVersion.status == "online")
    ).all()
    return sorted(s for s, d in rows if code in references(Definition.model_validate(d))[kind])


def online_strategy(db: Session, code: str):
    """(strategy id, version row id, version number, definition, context) of the online version, cached."""
    now = time.monotonic()
    with _lock:
        cached = _strategies.get(code)
        if cached and cached[0] > now:
            return cached[1]
    strategy = db.scalar(select(Strategy).where(Strategy.code == code))
    if strategy is None:
        return None
    version = db.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy.id, StrategyVersion.status == "online"
        )
    )
    if version is None:
        return None
    definition = Definition.model_validate(version.definition)
    value = (strategy.id, version.id, version.version, definition, context_for(db, definition))
    with _lock:
        _strategies[code] = (now + TTL_SECONDS, value)
    return value


def invalidate(code: str | None = None) -> None:
    with _lock:
        if code is None:
            _strategies.clear()
        else:
            _strategies.pop(code, None)
