"""Browser profile persistence for nodriver, backed by MinIO.

The nodriver user-data-dir (cookies, local storage, login session) is kept
as a single zip object in MinIO instead of on local/container disk, so a
logged-in session survives across task runs and container restarts without
baking credentials/session state into the image or the repo root.
"""

import contextlib
import io
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.core.config.config import get_settings
from app.core.jobs.minio_client import get_minio_client
from app.core.logging.logging import get_logger

logger = get_logger(__name__)


@contextlib.contextmanager
def load_profile() -> Iterator[Path]:
    """Materialize the browser profile into a fresh temp dir for the duration of a task.

    Yields the profile directory to use as nodriver's user-data-dir. On exit,
    re-zips and uploads the (possibly updated, e.g. refreshed cookies) profile
    back to MinIO — even if the caller's task body raised, so partial
    progress (e.g. cookies from steps that did complete) isn't silently lost
    while a flow is still being worked out — then deletes the temp dir so
    nothing persists on local disk. If no profile exists yet in MinIO (first
    run), yields an empty dir that nodriver will populate from scratch.
    """
    settings = get_settings()
    client = get_minio_client()
    profile_dir = Path(tempfile.mkdtemp(prefix="nodriver-profile-"))

    try:
        try:
            response = client.get_object(
                settings.minio_profile_bucket, settings.minio_profile_object
            )
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(profile_dir)
            logger.info("Loaded browser profile from minio://%s/%s",
                        settings.minio_profile_bucket, settings.minio_profile_object)
        except S3Error as exc:
            if exc.code == "NoSuchKey" or exc.code == "NoSuchBucket":
                logger.info("No existing browser profile in MinIO; starting fresh")
            else:
                raise

        try:
            yield profile_dir
        finally:
            _save_profile(client, profile_dir)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def _save_profile(client: Minio, profile_dir: Path) -> None:
    settings = get_settings()

    if not client.bucket_exists(settings.minio_profile_bucket):
        client.make_bucket(settings.minio_profile_bucket)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in profile_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(profile_dir))
    buffer.seek(0)

    size = buffer.getbuffer().nbytes
    client.put_object(
        settings.minio_profile_bucket,
        settings.minio_profile_object,
        buffer,
        length=size,
    )
    logger.info("Saved browser profile to minio://%s/%s (%d bytes)",
                settings.minio_profile_bucket, settings.minio_profile_object, size)
