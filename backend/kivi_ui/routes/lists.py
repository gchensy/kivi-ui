"""Watchlists (black, white, grey). Values are kept only as HMAC digests and masked text."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from .. import audit
from ..deps import CurrentUser, Db
from ..errors import ApiError
from ..models import RiskList, RiskListItem
from ..rules import runtime
from ..rules.engine import mask_text, normalise_value
from ..strategy_schemas import (
    AddItemsOut,
    CheckIn,
    CheckOut,
    ItemOut,
    ItemPage,
    ItemsIn,
    ListCreateIn,
    ListOut,
    ListUpdateIn,
)
from .datasets import ensure_owner

router = APIRouter(prefix="/risk-lists", tags=["watchlists"])


def get_list(db: Db, list_id: uuid.UUID) -> RiskList:
    found = db.get(RiskList, list_id)
    if found is None:
        raise ApiError(404, "list_not_found", "Watchlist not found")
    return found


def with_counts(db: Db, lists: list[RiskList]) -> list[ListOut]:
    now = datetime.now(UTC)
    ids = [x.id for x in lists]
    totals = dict(
        db.execute(
            select(RiskListItem.list_id, func.count())
            .where(RiskListItem.list_id.in_(ids))
            .group_by(RiskListItem.list_id)
        ).all()
    )
    active = dict(
        db.execute(
            select(RiskListItem.list_id, func.count())
            .where(
                RiskListItem.list_id.in_(ids),
                or_(RiskListItem.expires_at.is_(None), RiskListItem.expires_at > now),
            )
            .group_by(RiskListItem.list_id)
        ).all()
    )
    return [
        ListOut.model_validate(x).model_copy(
            update={"item_count": totals.get(x.id, 0), "active_count": active.get(x.id, 0)}
        )
        for x in lists
    ]


@router.get("", response_model=list[ListOut])
def list_lists(_: CurrentUser, db: Db) -> list[ListOut]:
    return with_counts(db, list(db.scalars(select(RiskList).order_by(RiskList.code)).unique()))


@router.post("", response_model=ListOut, status_code=status.HTTP_201_CREATED)
def create_list(body: ListCreateIn, request: Request, user: CurrentUser, db: Db) -> ListOut:
    if db.scalar(select(RiskList.id).where(RiskList.code == body.code)):
        raise ApiError(409, "code_taken", "A watchlist with this code already exists")
    created = RiskList(**body.model_dump(), owner_id=user.id)
    db.add(created)
    db.flush()
    audit.record(
        db,
        "list.created",
        actor=user,
        request=request,
        entity_type="list",
        entity_id=created.id,
        code=created.code,
    )
    db.commit()
    db.refresh(created)
    return with_counts(db, [created])[0]


@router.get("/{list_id}", response_model=ListOut)
def get_one(list_id: uuid.UUID, _: CurrentUser, db: Db) -> ListOut:
    return with_counts(db, [get_list(db, list_id)])[0]


@router.patch("/{list_id}", response_model=ListOut)
def update_list(
    list_id: uuid.UUID, body: ListUpdateIn, request: Request, user: CurrentUser, db: Db
) -> ListOut:
    found = get_list(db, list_id)
    ensure_owner(user, found.owner_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(found, key, value.strip() if isinstance(value, str) else value)
    audit.record(
        db,
        "list.updated",
        actor=user,
        request=request,
        entity_type="list",
        entity_id=found.id,
        code=found.code,
        fields=sorted(changes),
    )
    db.commit()
    return with_counts(db, [found])[0]


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: uuid.UUID, request: Request, user: CurrentUser, db: Db) -> None:
    found = get_list(db, list_id)
    ensure_owner(user, found.owner_id)
    if users := runtime.online_strategies_using(db, "lists", found.code):
        raise ApiError(409, "list_in_use", "An online strategy uses this watchlist", {"strategies": users})
    code = found.code
    db.delete(found)
    audit.record(
        db, "list.deleted", actor=user, request=request, entity_type="list", entity_id=list_id, code=code
    )
    db.commit()
    runtime.invalidate()


@router.get("/{list_id}/items", response_model=ItemPage)
def list_items(
    list_id: uuid.UUID,
    _: CurrentUser,
    db: Db,
    q: str | None = Query(None, max_length=256),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
) -> ItemPage:
    get_list(db, list_id)
    query = select(RiskListItem).where(RiskListItem.list_id == list_id)
    if q and (text := normalise_value(q)):
        query = query.where(RiskListItem.value_hash == runtime.hasher()(text))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = (
        db.scalars(query.order_by(RiskListItem.id.desc()).offset((page - 1) * size).limit(size))
        .unique()
        .all()
    )
    return ItemPage(items=[ItemOut.model_validate(i) for i in items], total=total)


@router.post("/{list_id}/items", response_model=AddItemsOut, status_code=status.HTTP_201_CREATED)
def add_items(list_id: uuid.UUID, body: ItemsIn, request: Request, user: CurrentUser, db: Db) -> AddItemsOut:
    found = get_list(db, list_id)
    digest = runtime.hasher()
    rows, seen = [], set()
    for raw in body.values:
        text = normalise_value(raw)
        if not text:
            continue
        value_hash = digest(text)
        if value_hash in seen:
            continue
        seen.add(value_hash)
        rows.append(
            {
                "list_id": found.id,
                "value_hash": value_hash,
                "value_masked": mask_text(text),
                "reason": body.reason.strip(),
                "expires_at": body.expires_at,
                "created_by": user.id,
            }
        )
    added = 0
    if rows:
        result = db.execute(
            insert(RiskListItem)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["list_id", "value_hash"])
            .returning(RiskListItem.id)
        )
        added = len(result.all())
    found.updated_at = datetime.now(UTC)
    audit.record(
        db,
        "list.items_added",
        actor=user,
        request=request,
        entity_type="list",
        entity_id=found.id,
        code=found.code,
        count=added,
    )
    db.commit()
    runtime.invalidate()
    return AddItemsOut(added=added, skipped=len(body.values) - added)


@router.delete("/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(list_id: uuid.UUID, item_id: int, request: Request, user: CurrentUser, db: Db) -> None:
    found = get_list(db, list_id)
    item = db.get(RiskListItem, item_id)
    if item is None or item.list_id != found.id:
        raise ApiError(404, "item_not_found", "Watchlist entry not found")
    masked = item.value_masked
    db.delete(item)
    audit.record(
        db,
        "list.item_removed",
        actor=user,
        request=request,
        entity_type="list",
        entity_id=found.id,
        code=found.code,
        value=masked,
    )
    db.commit()
    runtime.invalidate()


@router.post("/{list_id}/check", response_model=CheckOut)
def check(list_id: uuid.UUID, body: CheckIn, _: CurrentUser, db: Db) -> CheckOut:
    found = get_list(db, list_id)
    text = normalise_value(body.value)
    if not text:
        return CheckOut(listed=False)
    now = datetime.now(UTC)
    item = db.scalar(
        select(RiskListItem).where(
            RiskListItem.list_id == found.id,
            RiskListItem.value_hash == runtime.hasher()(text),
            or_(RiskListItem.expires_at.is_(None), RiskListItem.expires_at > now),
        )
    )
    return CheckOut(listed=item is not None, item=ItemOut.model_validate(item) if item else None)
