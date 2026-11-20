"""The review lifecycle shared by model versions and strategy versions."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..errors import ApiError
from ..models import Role, User

# action -> (allowed from, new status, administrators only)
TRANSITIONS = {
    "submit": ({"draft"}, "in_review", False),
    "approve": ({"in_review"}, "approved", True),
    "reject": ({"in_review"}, "draft", True),
    "online": ({"approved"}, "online", True),
    "retire": ({"approved", "online"}, "retired", True),
}


def transition(
    db: Session, version: Any, action: str, user: User, comment: str, *, parent: str, review_cls: type
) -> Any | None:
    """Apply `action` to `version`; returns the version it replaced online, if any.

    `parent` names the foreign key shared by sibling versions (model_id, strategy_id);
    `review_cls` is the review-trail model with version_id, action, actor_id, comment.
    """
    if action not in TRANSITIONS:
        raise ApiError(404, "not_found", "Unknown action")
    allowed, target, admin_only = TRANSITIONS[action]
    if admin_only and user.role is not Role.admin:
        raise ApiError(403, "forbidden", "Administrator role required")
    if action == "submit" and user.role is not Role.admin and version.created_by != user.id:
        raise ApiError(403, "forbidden", "Only the author or an administrator can submit this version")
    if version.status not in allowed:
        raise ApiError(
            409,
            "invalid_transition",
            f"Cannot {action} a version that is {version.status}",
            {"status": version.status},
        )
    if (
        action == "approve"
        and get_settings().require_four_eyes
        and user.id in {version.submitted_by, version.created_by}
    ):
        raise ApiError(403, "four_eyes", "The author or submitter cannot approve their own version")

    now = datetime.now(UTC)
    replaced = None
    if action == "submit":
        version.submitted_by, version.submitted_at = user.id, now
    elif action == "approve":
        version.approved_by, version.approved_at = user.id, now
    elif action == "reject":
        version.submitted_by = version.submitted_at = None
    elif action == "online":
        cls = type(version)
        replaced = db.scalar(
            select(cls).where(getattr(cls, parent) == getattr(version, parent), cls.status == "online")
        )
        if replaced is not None:
            replaced.status, replaced.retired_at = "retired", now
            db.add(
                review_cls(
                    version_id=replaced.id,
                    action="retire",
                    actor_id=user.id,
                    comment=f"replaced by v{version.version}",
                )
            )
            db.flush()
        version.online_at = now
    elif action == "retire":
        version.retired_at = now
    version.status = target
    db.add(review_cls(version_id=version.id, action=action, actor_id=user.id, comment=comment.strip()))
    return replaced
