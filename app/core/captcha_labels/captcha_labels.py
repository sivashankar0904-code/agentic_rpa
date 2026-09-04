"""Captcha ground-truth labels table, backed by an external Postgres instance.

The database itself is provisioned and maintained outside this service (see
app/core/config/config.py's db_* fields / captcha_labels_database_url); its
schema lives in schemas/captcha_labels.sql, applied once by hand against that
database — this codebase has no migrations framework yet. Data access goes
through the SQLAlchemy ORM model in app/core/captcha_labels/models.py.

Lifecycle: gst_login captures a captcha, uploads it to MinIO, and immediately
inserts an unlabeled row here (object_name set, label NULL, is_solved false).
A human then fills in `label` and flips `is_solved` to true, either via the
captcha-labels API (see app/core/captcha_labels/captcha_label_service.py) or
by hand. The training task only ever reads rows where is_solved is true.
"""

from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.captcha_labels.models import CaptchaLabel
from app.core.config.config import get_settings
from app.core.logging.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _get_engine():
    return create_engine(get_settings().captcha_labels_database_url)


def record_captcha(object_name: str) -> None:
    """Insert an unlabeled row for a freshly-captured captcha.

    Called right after captcha_store.save_captcha() uploads the image, so
    every object in the rpa-captchas MinIO bucket has a corresponding row
    here (initially unsolved) for a human to label later. created_at/
    updated_at have no DB-side default (see schemas/captcha_labels.sql) —
    the model sets both here. Uses an ON CONFLICT DO NOTHING upsert (rather
    than a plain ORM add()) so retrying an already-recorded object_name is
    a safe no-op.
    """
    now = datetime.now(timezone.utc)

    with Session(_get_engine()) as session:
        stmt = (
            pg_insert(CaptchaLabel)
            .values(object_name=object_name, created_at=now, updated_at=now)
            .on_conflict_do_nothing(index_elements=["object_name"])
        )
        session.execute(stmt)
        session.commit()

    logger.info("Recorded captcha minio://%s awaiting a label", object_name)


def fetch_labeled_captchas() -> list[tuple[str, str]]:
    """Return (object_name, label) pairs for every manually-solved captcha."""
    with Session(_get_engine()) as session:
        rows = session.scalars(
            select(CaptchaLabel).where(
                CaptchaLabel.is_solved.is_(True),
                CaptchaLabel.label.is_not(None),
            )
        ).all()

    logger.info("Fetched %d labeled captchas from Postgres", len(rows))
    return [(row.object_name, row.label) for row in rows]


def fetch_unsolved_captchas() -> list[CaptchaLabel]:
    """Return every captured captcha still awaiting a manual label."""
    with Session(_get_engine()) as session:
        rows = session.scalars(
            select(CaptchaLabel)
            .where(CaptchaLabel.is_solved.is_(False))
            .order_by(CaptchaLabel.created_at)
        ).all()
        session.expunge_all()

    return list(rows)


def fetch_captcha(object_name: str) -> CaptchaLabel | None:
    """Return one captcha_labels row, or None if object_name isn't on record."""
    with Session(_get_engine()) as session:
        row = session.get(CaptchaLabel, object_name)
        if row is not None:
            session.expunge(row)

    return row


def record_prediction(object_name: str, predicted_label: str, accuracy: float) -> None:
    """Store validator-worker's prediction + character-match accuracy for
    one already-solved captcha (see app/tasks/validator_tasks.py).

    No-op (with a warning) if object_name isn't on record — validation runs
    off a snapshot of fetch_labeled_captchas(), so this should never
    actually happen, but a row could in principle disappear between the
    fetch and the write-back.
    """
    with Session(_get_engine()) as session:
        row = session.get(CaptchaLabel, object_name)
        if row is None:
            logger.warning("record_prediction: %s not found, skipping", object_name)
            return

        row.predicted_label = predicted_label
        row.accuracy = accuracy
        session.commit()


def solve_captcha(object_name: str, label: str) -> CaptchaLabel | None:
    """Record a human-entered label and mark the row solved.

    Returns the updated row, or None if object_name isn't on record (the
    caller should treat that as a 404 rather than silently no-op-ing).
    """
    now = datetime.now(timezone.utc)

    with Session(_get_engine()) as session:
        row = session.get(CaptchaLabel, object_name)
        if row is None:
            return None

        row.label = label
        row.is_solved = True
        row.updated_at = now
        session.commit()
        session.refresh(row)
        session.expunge(row)

    logger.info("Solved captcha minio://%s", object_name)
    return row
