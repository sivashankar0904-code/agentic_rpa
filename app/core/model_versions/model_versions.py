"""Captcha CNN training-run history, backed by the same external Postgres
instance as app/core/captcha_labels/.

One row per train_captcha_model run (see schemas/model_versions.sql). Not
a replacement for the captcha-cnn-latest.pt MinIO alias
(app/core/jobs/captcha_model_store.py) — this table is the queryable
history/metadata (which run produced which object, with what metrics), the
alias is a zero-query convenience for a future inference step to grab
current weights without querying this table at all.
"""

from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config.config import get_settings
from app.core.logging.logging import get_logger
from app.core.model_versions.models import ModelVersion

logger = get_logger(__name__)


@lru_cache
def _get_engine():
    return create_engine(get_settings().captcha_labels_database_url)


def record_model_version(
    minio_object_name: str,
    sample_count: int,
    final_loss: float | None = None,
    final_accuracy: float | None = None,
    mlflow_run_id: str | None = None,
) -> None:
    """Insert one row for a just-completed training run."""
    with Session(_get_engine()) as session:
        session.add(
            ModelVersion(
                minio_object_name=minio_object_name,
                sample_count=sample_count,
                final_loss=final_loss,
                final_accuracy=final_accuracy,
                mlflow_run_id=mlflow_run_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    logger.info("Recorded model version minio://%s (%d samples)", minio_object_name, sample_count)


def fetch_latest_model_version() -> ModelVersion | None:
    """Return the most recently trained model's row, or None if none exist."""
    with Session(_get_engine()) as session:
        row = session.scalars(
            select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(1)
        ).first()
        if row is not None:
            session.expunge(row)

    return row


def fetch_model_versions() -> list[ModelVersion]:
    """Return every training run's row, newest first."""
    with Session(_get_engine()) as session:
        rows = session.scalars(
            select(ModelVersion).order_by(ModelVersion.created_at.desc())
        ).all()
        session.expunge_all()

    return list(rows)
