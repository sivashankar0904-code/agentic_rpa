"""Captcha-solving inference Celery tasks — the "predict" queue.

Only imported by the predict-worker service (see docker/entrypoint.sh's
--include app.tasks.predict_tasks), a third worker image separate from both
rpa-worker (nodriver/Chromium) and training-worker (the full torch +
mlflow training stack): inference is lightweight and interactive (called
synchronously from an API request, see captcha_label_service.py), so it
shouldn't queue behind a 60-epoch training run on the same worker.
"""

from app.celery_app import celery_app
from app.core.jobs.captcha_model_store import download_latest_model
from app.core.jobs.captcha_store import download_captcha
from app.core.logging.logging import get_logger
from app.core.ml.predict import predict_captcha as _predict_captcha

logger = get_logger(__name__)


@celery_app.task(name="agentic_rpa.predict_captcha")
def predict_captcha(object_name: str) -> dict:
    """Predict a captcha's text using the current captcha-cnn-latest.pt model.

    Flow: download the latest trained model from the rpa-captcha-models
    MinIO bucket -> download the requested captcha image from rpa-captchas
    -> run inference -> return the predicted text. Called synchronously
    (task.get()) from POST /api/v1/captcha-labels/{object_name}/predict, not
    on a schedule.
    """
    model_bytes = download_latest_model()
    image_bytes = download_captcha(object_name)

    predicted_label = _predict_captcha(model_bytes, image_bytes)
    logger.info("Predicted %r for minio://%s", predicted_label, object_name)

    return {"object_name": object_name, "predicted_label": predicted_label}
