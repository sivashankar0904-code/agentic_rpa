"""Post-training model validation Celery tasks — the "validate" queue.

Only imported by the validator-worker service (see docker/entrypoint.sh's
--include app.tasks.validator_tasks). Deliberately lightweight: this worker
calls the predict API over HTTP rather than running inference itself, so it
needs no torch (unlike training-worker/predict-worker) — just requests and
Postgres access for reading labels / writing predictions back.
"""

import requests

from app.celery_app import celery_app
from app.core.captcha_labels.captcha_labels import fetch_labeled_captchas, record_prediction
from app.core.config.config import get_settings
from app.core.logging.logging import get_logger

logger = get_logger(__name__)

_PREDICT_TIMEOUT_SECONDS = 30


def _char_accuracy(predicted_label: str, true_label: str) -> float:
    """Fraction of characters that match at the same position.

    Compares position-by-position up to the shorter of the two strings —
    a length mismatch (see captcha_cnn.py's CAPTCHA_LENGTH docstring on why
    that can happen) still yields a meaningful partial score instead of
    crashing or silently scoring 0.
    """
    if not true_label:
        return 0.0

    matches = sum(
        1 for predicted_char, true_char in zip(predicted_label, true_label)
        if predicted_char == true_char
    )
    return matches / len(true_label)


@celery_app.task(name="agentic_rpa.validate_captchas")
def validate_captchas() -> dict:
    """Re-predict every solved captcha with the just-trained model and
    record how well it did.

    Flow: read every (object_name, label) pair from the captcha_labels
    table (the same set train_captcha_model just trained on) -> for each,
    POST the captcha-labels API's predict endpoint (app/api/v1/
    captcha_label_api.py's predictCaptcha route, which itself routes to
    predict-worker) -> compare the prediction against the true label
    character-by-character -> write predicted_label + accuracy back onto
    that row (app/core/captcha_labels/captcha_labels.py's
    record_prediction). Enqueued automatically by train_captcha_model on
    successful completion (see app/tasks/training_tasks.py), not on a
    schedule of its own.
    """
    settings = get_settings()
    labeled = fetch_labeled_captchas()
    logger.info("Validating model against %d labeled captchas", len(labeled))

    validated = 0
    failed = 0
    accuracies: list[float] = []

    for object_name, true_label in labeled:
        url = f"{settings.api_base_url}/api/v1/captcha-labels/{object_name}/predict"
        try:
            response = requests.post(url, timeout=_PREDICT_TIMEOUT_SECONDS)
            response.raise_for_status()
            predicted_label = response.json()["predicted_label"]
        except requests.RequestException as error:
            logger.warning("Predict failed for %s: %s", object_name, error)
            failed += 1
            continue

        accuracy = _char_accuracy(predicted_label, true_label)
        record_prediction(object_name, predicted_label, accuracy)
        accuracies.append(accuracy)
        validated += 1

    average_accuracy = sum(accuracies) / len(accuracies) if accuracies else None
    logger.info(
        "Validation complete: %d validated, %d failed, average accuracy %s",
        validated, failed, average_accuracy,
    )

    return {
        "validated": validated,
        "failed": failed,
        "average_accuracy": average_accuracy,
    }
