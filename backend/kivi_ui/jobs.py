"""A small PostgreSQL-backed job queue.

Jobs are rows in ``jobs``. A worker claims the oldest queued row with
``FOR UPDATE SKIP LOCKED``, so several workers (threads or processes) never
take the same job. Handlers are registered by kind and receive a fresh session.
"""

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from .db import get_sessionmaker
from .models import Job, User

log = logging.getLogger("kivi_ui.jobs")
Handler = Callable[[Session, Job], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


class JobFailed(Exception):
    """Raised by a handler to fail the job with a user-facing message."""


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(db: Session, kind: str, params: dict[str, Any], user: User | None) -> Job:
    job = Job(kind=kind, params=params, created_by=user.id if user else None)
    db.add(job)
    db.flush()
    return job


def _claim(db: Session) -> Job | None:
    job_id = db.execute(
        text(
            "UPDATE jobs SET status = 'running', started_at = now() WHERE id = ("
            " SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at"
            " FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id"
        )
    ).scalar()
    db.commit()
    return db.get(Job, job_id) if job_id else None


def run_one() -> uuid.UUID | None:
    """Claim and run one queued job. Returns its id, or None when the queue is empty."""
    maker = get_sessionmaker()
    with maker() as db:
        job = _claim(db)
        if job is None:
            return None
        job_id, kind = job.id, job.kind
    with maker() as db:
        job = db.get(Job, job_id)
        try:
            fn = HANDLERS.get(kind)
            if fn is None:
                raise JobFailed(f"No handler for job kind {kind!r}")
            result = fn(db, job)
            job.status, job.result, job.progress = "done", result, 1.0
        except Exception as error:  # noqa: BLE001 - every failure is recorded on the job
            db.rollback()
            job = db.get(Job, job_id)
            job.status = "failed"
            job.error = (
                str(error)[:2000]
                if isinstance(error, JobFailed)
                else f"{type(error).__name__}: {error}"[:2000]
            )
            log.warning("job %s (%s) failed:\n%s", job_id, kind, traceback.format_exc())
            on_failure = FAILURE_HOOKS.get(kind)
            if on_failure:
                on_failure(db, job)
        job.finished_at = datetime.now(UTC)
        db.commit()
    return job_id


def run_pending(limit: int = 100) -> int:
    count = 0
    while count < limit and run_one() is not None:
        count += 1
    return count


FAILURE_HOOKS: dict[str, Callable[[Session, Job], None]] = {}


def on_failure(kind: str):
    def register(fn: Callable[[Session, Job], None]):
        FAILURE_HOOKS[kind] = fn
        return fn

    return register


def requeue_stale(minutes: int = 30) -> None:
    """Jobs left running by a stopped process go back on the queue."""
    with get_sessionmaker()() as db:
        db.execute(
            update(Job)
            .where(
                Job.status == "running", Job.started_at < text(f"now() - interval '{int(minutes)} minutes'")
            )
            .values(status="queued", started_at=None)
        )
        db.commit()


class Worker(threading.Thread):
    """Polls the queue until stopped. Started by the API (see main.py) or `kivi-ui worker`."""

    def __init__(self, interval: float = 1.0):
        super().__init__(name="kivi-ui-worker", daemon=True)
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self) -> None:
        requeue_stale()
        while not self.stop_event.is_set():
            try:
                if run_one() is None:
                    self.stop_event.wait(self.interval)
            except Exception:  # noqa: BLE001 - keep the loop alive across database hiccups
                log.exception("worker loop error")
                self.stop_event.wait(5)

    def stop(self) -> None:
        self.stop_event.set()


def get_job(db: Session, job_id: uuid.UUID) -> Job | None:
    return db.scalar(select(Job).where(Job.id == job_id))
