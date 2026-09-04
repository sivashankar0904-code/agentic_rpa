"""Training-run lock/audit trail, backed by the same external Postgres
instance as app/core/captcha_labels/ and app/core/model_versions/.

Prevents the beat-scheduled trigger_train_captcha_model (every 10 minutes,
see app/tasks/training_tasks.py) from stacking a new training run on top of
one still in progress: train_captcha_model checks is_any_training_in_progress()
before starting, and wraps the run between start_training_run()/
complete_training_run() so a crash still releases the lock instead of
blocking every future attempt forever.

That finally block only fires on a Python-level exception, not on the
worker process itself dying (container restart, OOM, crash) — a row left
is_completed=false by a killed process would otherwise block every future
training run indefinitely. is_any_training_in_progress() treats a row as
stale (not actually blocking) once it's older than
training_schedule_stale_after_seconds, so this self-heals without a manual
DB fix; see config.py's comment for why that threshold is safe.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config.config import get_settings
from app.core.logging.logging import get_logger
from app.core.model_versions.training_schedule_models import TrainingScheduleEntry

logger = get_logger(__name__)


@lru_cache
def _get_engine():
    return create_engine(get_settings().captcha_labels_database_url)


def is_any_training_in_progress() -> bool:
    """True if some training_schedule row is still is_completed = false
    and not old enough to be considered stale (see module docstring)."""
    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=get_settings().training_schedule_stale_after_seconds
    )

    with Session(_get_engine()) as session:
        in_progress = session.scalars(
            select(TrainingScheduleEntry).where(
                TrainingScheduleEntry.is_completed.is_(False),
                TrainingScheduleEntry.started_at > stale_cutoff,
            )
        ).first()

    return in_progress is not None


def start_training_run() -> int:
    """Insert a new in-progress row and return its id."""
    with Session(_get_engine()) as session:
        entry = TrainingScheduleEntry(
            started_at=datetime.now(timezone.utc),
            is_completed=False,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        run_id = entry.id

    logger.info("Started training_schedule run %d", run_id)
    return run_id


def complete_training_run(run_id: int) -> None:
    """Mark a training_schedule row completed, releasing the lock."""
    with Session(_get_engine()) as session:
        entry = session.get(TrainingScheduleEntry, run_id)
        if entry is None:
            logger.warning("training_schedule run %d not found — nothing to complete", run_id)
            return

        entry.completed_at = datetime.now(timezone.utc)
        entry.is_completed = True
        session.commit()

    logger.info("Completed training_schedule run %d", run_id)
