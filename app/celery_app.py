from celery import Celery

from app.core.config.config import get_settings

settings = get_settings()

# No app-level `include` here on purpose: rpa_tasks.py (nodriver/Chromium),
# training_tasks.py (torch/numpy/pillow/mlflow), predict_tasks.py
# (torch/numpy/pillow, no mlflow), and validator_tasks.py (requests +
# Postgres only, no torch) each live in their own worker image
# (Dockerfile / Dockerfile.training / Dockerfile.predict /
# Dockerfile.validator) and are loaded only via that worker's own
# `celery worker --include app.tasks.<module>` (see docker/entrypoint.sh) —
# importing all of them here would force every process that touches this
# module (api, beat, flower included) to have every dependency set installed.
celery_app = Celery(
    "agentic_rpa",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    # Route each task to the worker that actually has its dependencies
    # installed — rpa-worker consumes "rpa", training-worker consumes
    # "training", predict-worker consumes "predict", validator-worker
    # consumes "validate" (see docker-compose.yml).
    task_routes={
        "agentic_rpa.gst_login": {"queue": "rpa"},
        "agentic_rpa.trigger_gst_login": {"queue": "rpa"},
        "agentic_rpa.train_captcha_model": {"queue": "training"},
        "agentic_rpa.trigger_train_captcha_model": {"queue": "training"},
        "agentic_rpa.predict_captcha": {"queue": "predict"},
        "agentic_rpa.validate_captchas": {"queue": "validate"},
    },
    beat_schedule={
        "trigger-gst-login-every-30s": {
            "task": "agentic_rpa.trigger_gst_login",
            "schedule": 30.0,
        },
        # train_captcha_model itself skips the run (see
        # app/tasks/training_tasks.py) if training_schedule shows one
        # already in progress, so overlapping attempts can't stack no
        # matter how short this interval is set. Configurable via
        # AGENTIC_RPA_TRAINING_SCHEDULE_INTERVAL_SECONDS (default 600 = 10m).
        "trigger-train-captcha-model": {
            "task": "agentic_rpa.trigger_train_captcha_model",
            "schedule": settings.training_schedule_interval_seconds,
        },
    },
)
