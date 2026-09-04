"""Business layer for the manual captcha-labeling workflow.

Thin ServiceResponse-wrapping layer over captcha_labels.py's raw data
access, mirroring app/core/jobs/jobs.py's role for job_schema/job_api.
"""

from celery.exceptions import TimeoutError as CeleryTimeoutError
from minio.error import S3Error

from app.celery_app import celery_app
from app.core.captcha_labels import captcha_labels as captcha_labels_store
from app.core.jobs.captcha_store import download_captcha
from app.core.logging.logging import get_logger
from app.core.response import ServiceResponse, ServiceStatus
from app.schemas.captcha_label_schema import CaptchaLabelRead, CaptchaPredictionRead

logger = get_logger(__name__)

# Inference is fast (a single forward pass), but the predict-worker still
# has to pull the latest model + this image from MinIO first — 30s gives
# headroom without hanging an HTTP request indefinitely if predict-worker
# is down or backed up.
_PREDICT_TIMEOUT_SECONDS = 30


def list_unsolved_captchas() -> ServiceResponse[list[CaptchaLabelRead]]:
    rows = captcha_labels_store.fetch_unsolved_captchas()
    return ServiceResponse(
        status=ServiceStatus.SUCCESS,
        data=[CaptchaLabelRead.model_validate(row) for row in rows],
    )


def solve_captcha(object_name: str, label: str) -> ServiceResponse[CaptchaLabelRead]:
    row = captcha_labels_store.solve_captcha(object_name, label)
    if row is None:
        return ServiceResponse(status=ServiceStatus.NOT_FOUND)
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=CaptchaLabelRead.model_validate(row))


def get_captcha_image(object_name: str) -> ServiceResponse[bytes]:
    """Fetch a captcha's raw PNG bytes from MinIO for the labeling UI's <img>."""
    try:
        image_bytes = download_captcha(object_name)
    except S3Error as error:
        if error.code == "NoSuchKey":
            return ServiceResponse(status=ServiceStatus.NOT_FOUND)
        raise
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=image_bytes)


def predict_captcha(object_name: str) -> ServiceResponse[CaptchaPredictionRead]:
    """Run the current model against one captcha and return its prediction.

    Enqueues onto predict-worker (queue "predict") via send_task rather than
    importing predict_tasks.py directly — this process (api) has no torch
    installed, same reasoning as enqueue_train_captcha_model in jobs.py.
    Blocks for the result since inference is fast and the caller wants the
    prediction directly, not a task id to poll (see label_ui.py/
    captcha_label_api.py callers).
    """
    result = celery_app.send_task("agentic_rpa.predict_captcha", args=[object_name])
    try:
        prediction = result.get(timeout=_PREDICT_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        logger.error("predict_captcha timed out for %s", object_name)
        return ServiceResponse(status=ServiceStatus.TIMEOUT)

    return ServiceResponse(status=ServiceStatus.SUCCESS, data=CaptchaPredictionRead(**prediction))
