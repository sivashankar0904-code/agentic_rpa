"""Captcha image persistence, backed by MinIO.

Unlike the browser profile (long-lived session state, load+save round trip),
a captcha screenshot is a one-shot, per-run artifact: captured once during
login, uploaded, done. Kept in its own bucket so it isn't mixed in with
reusable profile data.
"""

import io

from app.core.config.config import get_settings
from app.core.jobs.minio_client import get_minio_client
from app.core.logging.logging import get_logger

logger = get_logger(__name__)


def save_captcha(task_id: str, image_bytes: bytes) -> str:
    """Upload a captcha screenshot to MinIO and return its object key."""
    settings = get_settings()
    client = get_minio_client()

    if not client.bucket_exists(settings.minio_captcha_bucket):
        client.make_bucket(settings.minio_captcha_bucket)

    object_name = f"{task_id}.png"
    client.put_object(
        settings.minio_captcha_bucket,
        object_name,
        io.BytesIO(image_bytes),
        length=len(image_bytes),
        content_type="image/png",
    )
    logger.info("Saved captcha to minio://%s/%s (%d bytes)",
                settings.minio_captcha_bucket, object_name, len(image_bytes))
    return object_name
