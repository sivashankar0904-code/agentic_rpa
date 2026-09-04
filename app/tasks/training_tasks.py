"""Captcha-model training Celery tasks — the "training" queue.

Only imported by the training-worker service (see docker/entrypoint.sh's
--include app.tasks.training_tasks), which is the only image with torch/
numpy/pillow installed (Dockerfile.training). Keep this module free of
nodriver/Chromium imports — those belong in rpa_tasks.py, imported only by
the rpa-worker image (Dockerfile).
"""

from datetime import datetime, timezone

import requests

from app.celery_app import celery_app
from app.core.captcha_labels.captcha_labels import fetch_labeled_captchas
from app.core.config.config import get_settings
from app.core.jobs.captcha_model_store import save_model
from app.core.jobs.captcha_store import download_captcha
from app.core.logging.logging import get_logger
from app.core.ml.captcha_cnn import CAPTCHA_LENGTH
from app.core.ml.train import train_captcha_model as _train_captcha_model
from app.core.model_versions.model_versions import record_model_version
from app.core.model_versions.training_schedule import (
    complete_training_run,
    is_any_training_in_progress,
    start_training_run,
)

logger = get_logger(__name__)


@celery_app.task(name="agentic_rpa.train_captcha_model")
def train_captcha_model() -> dict:
    """Train the captcha-solving CNN from labeled captchas and save it to MinIO.

    Flow: skip entirely if training_schedule shows a run already in
    progress (see app/core/model_versions/training_schedule.py — guards
    against the beat-scheduled trigger below stacking overlapping runs) ->
    read (object_name, label) pairs from the external Postgres labels table
    -> download each labeled image from the rpa-captchas MinIO bucket ->
    train a CaptchaCNN (app/core/ml/) on the FULL current labeled set
    (always from scratch, not incremental — see model_versions.py's
    docstring for why) -> upload the resulting weights to the
    rpa-captcha-models MinIO bucket (both a timestamped object and the
    captcha-cnn-latest.pt alias) -> record this run in the model_versions
    table for queryable history. Reachable both manually (POST
    /api/v1/jobs/train-captcha-model) and via the beat schedule below.
    Synchronous/CPU-bound throughout (no nodriver/async involved), unlike
    gst_login.
    """
    if is_any_training_in_progress():
        logger.info("Skipping train_captcha_model — a run is already in progress")
        return {"skipped": True, "reason": "training already in progress"}

    run_id = start_training_run()
    try:
        labeled = fetch_labeled_captchas()

        # Real GST captchas vary in length (confirmed against actual labeled
        # data — both 5- and 6-character labels seen), but CaptchaCNN is
        # fixed at CAPTCHA_LENGTH characters (see captcha_cnn.py's
        # docstring). Filter rather than crash the whole run over one
        # mismatched row; revisit with a real variable-length architecture
        # (padding/masking or CTC) if this drops too much data to be useful.
        wrong_length = [
            (object_name, label) for object_name, label in labeled
            if len(label.strip()) != CAPTCHA_LENGTH
        ]
        if wrong_length:
            logger.warning(
                "Skipping %d labeled captcha(s) with length != %d: %s",
                len(wrong_length), CAPTCHA_LENGTH,
                [(name, label) for name, label in wrong_length],
            )
        labeled = [
            (object_name, label) for object_name, label in labeled
            if len(label.strip()) == CAPTCHA_LENGTH
        ]

        logger.info("Training captcha model on %d labeled samples", len(labeled))
        if not labeled:
            raise ValueError(
                f"No labeled captchas with length {CAPTCHA_LENGTH} to train on "
                f"({len(wrong_length)} skipped for wrong length)"
            )

        samples = [(download_captcha(object_name), label) for object_name, label in labeled]

        result = _train_captcha_model(samples)

        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        object_name = save_model(result.model_bytes, version)

        record_model_version(
            minio_object_name=object_name,
            sample_count=len(samples),
            final_loss=result.final_loss,
            final_accuracy=result.final_accuracy,
            mlflow_run_id=result.mlflow_run_id,
        )

        # Enqueue onto validator-worker (queue "validate") by name rather
        # than importing validator_tasks.py directly — same reasoning as
        # jobs.py's enqueue_* functions: this module has no need to import
        # a sibling worker's task module just to call it by name.
        celery_app.send_task("agentic_rpa.validate_captchas")

        return {
            "skipped": False,
            "model_object": object_name,
            "sample_count": len(samples),
            "final_loss": result.final_loss,
            "final_accuracy": result.final_accuracy,
        }
    finally:
        # Always releases the lock, even on failure — otherwise a single
        # crashed run would permanently block every future attempt.
        complete_training_run(run_id)


@celery_app.task(name="agentic_rpa.trigger_train_captcha_model")
def trigger_train_captcha_model() -> dict:
    """Beat-scheduled: POST the jobs API's enqueue-train-captcha-model endpoint.

    Goes over HTTP to app/api/v1/job_api.py's enqueueTrainCaptchaModel route
    (rather than calling the train_captcha_model task directly), mirroring
    trigger_gst_login's pattern — the actual in-progress check happens
    inside train_captcha_model itself (see its docstring), not here, so a
    manual POST to the same endpoint is guarded identically.
    """
    settings = get_settings()
    url = f"{settings.api_base_url}/api/v1/jobs/train-captcha-model"
    response = requests.post(url, timeout=10)
    response.raise_for_status()
    return response.json()
