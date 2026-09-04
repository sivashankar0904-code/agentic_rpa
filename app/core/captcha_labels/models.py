"""SQLAlchemy ORM model for the captcha_labels table.

Schema owned by schemas/captcha_labels.sql (applied by hand against the
external Postgres instance — no migrations framework in this codebase yet);
this model mirrors that DDL for use by captcha_labels.py's data-access layer.
Kept separate from app/schemas/captcha_label_schema.py's Pydantic
request/response models per this repo's schema/core split.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CaptchaLabel(Base):
    __tablename__ = "captcha_labels"

    object_name: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    is_solved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set by validator-worker after each training run (see
    # app/tasks/validator_tasks.py) — the model's guess and the fraction of
    # characters (0.0-1.0) that matched `label`.
    predicted_label: Mapped[str | None] = mapped_column(String, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
