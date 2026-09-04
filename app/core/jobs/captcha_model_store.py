"""Trained captcha-model artifact persistence, backed by MinIO.

Mirrors captcha_store.py's shape but for the CNN weights the training task
produces, kept in their own bucket rather than mixed in with either the raw
captcha screenshots or the browser profile.

Every training run's timestamped weights are kept (captcha-cnn-<version>.pt)
for history/rollback, and LATEST_MODEL_OBJECT is overwritten alongside it on
every successful run — a fixed, well-known object a future inference step
can load without needing to know the latest timestamp.
"""

import io

from app.core.config.config import get_settings
from app.core.jobs.minio_client import get_minio_client
from app.core.logging.logging import get_logger

logger = get_logger(__name__)

LATEST_MODEL_OBJECT = "captcha-cnn-latest.pt"


def save_model(model_bytes: bytes, version: str) -> str:
    """Upload trained model weights to MinIO, updating the latest alias too.

    Returns the timestamped object's key (not the latest alias) so callers
    can still record exactly which version a given training run produced.
    """
    settings = get_settings()
    client = get_minio_client()

    if not client.bucket_exists(settings.minio_model_bucket):
        client.make_bucket(settings.minio_model_bucket)

    object_name = f"captcha-cnn-{version}.pt"
    for name in (object_name, LATEST_MODEL_OBJECT):
        client.put_object(
            settings.minio_model_bucket,
            name,
            io.BytesIO(model_bytes),
            length=len(model_bytes),
            content_type="application/octet-stream",
        )
    logger.info(
        "Saved captcha model to minio://%s/%s (%d bytes), updated %s",
        settings.minio_model_bucket, object_name, len(model_bytes), LATEST_MODEL_OBJECT,
    )
    return object_name


def download_latest_model() -> bytes:
    """Download the current captcha-cnn-latest.pt weights for inference."""
    settings = get_settings()
    client = get_minio_client()

    response = client.get_object(settings.minio_model_bucket, LATEST_MODEL_OBJECT)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
