"""SQLAlchemy ORM model for the training_schedule table.

Schema owned by schemas/training_schedule.sql (applied by hand against the
external Postgres instance — no migrations framework in this codebase yet);
this model mirrors that DDL for use by training_schedule.py's data-access
layer. Mirrors app/core/captcha_labels/models.py's shape/conventions.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TrainingScheduleEntry(Base):
    __tablename__ = "training_schedule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
