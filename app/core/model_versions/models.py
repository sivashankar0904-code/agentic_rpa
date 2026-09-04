"""SQLAlchemy ORM model for the model_versions table.

Schema owned by schemas/model_versions.sql (applied by hand against the
external Postgres instance — no migrations framework in this codebase yet);
this model mirrors that DDL for use by model_versions.py's data-access layer.
Mirrors app/core/captcha_labels/models.py's shape/conventions.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    minio_object_name: Mapped[str] = mapped_column(String, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    final_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
