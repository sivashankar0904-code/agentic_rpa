from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Shared config for the API and Celery worker, sourced from env vars."""

    model_config = SettingsConfigDict(env_prefix="AGENTIC_RPA_", extra="ignore")

    app_name: str = "agentic_rpa"
    log_level: str = "INFO"

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    display: str = ":99"

    # Base URL the Celery beat scheduler uses to call back into this service's
    # own HTTP API (e.g. POST /api/v1/jobs/gst-login) rather than invoking the
    # Celery task directly. Defaults to the docker-compose service name/port.
    api_base_url: str = "http://api:8000"

    # GST portal RPA target: URL to navigate to, and credentials for the login step.
    gst_url: str = ""
    gst_username: str = ""
    gst_password: str = ""

    # MinIO holds the nodriver browser profile (cookies/session) as a zip so
    # a logged-in session survives across task runs without baking it into
    # the image or the repo. Downloaded to a temp dir at task start.
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_profile_bucket: str = "rpa-profiles"
    minio_profile_object: str = "gst-profile.zip"

    # Captcha screenshots are per-run artifacts, not session state, so they
    # get their own bucket (one object per task run) rather than living
    # alongside the reusable browser profile.
    minio_captcha_bucket: str = "rpa-captchas"

    # Trained captcha-solving model artifacts, produced by the
    # train_captcha_model task (see app/core/ml/).
    minio_model_bucket: str = "rpa-captcha-models"

    # MLflow tracking server: train.py logs per-epoch loss/accuracy plus the
    # final model artifact here so training runs are visible in the MLflow
    # UI, not just worker logs. Training-worker only (see
    # requirements-training.txt/Dockerfile.training) — the mlflow client
    # isn't installed anywhere else.
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment_name: str = "captcha-cnn"

    # How often beat fires trigger_train_captcha_model (see
    # app/celery_app.py's beat_schedule). train_captcha_model itself skips
    # the run if training_schedule shows one already in progress, so this
    # can be tuned freely without risking overlapping runs.
    training_schedule_interval_seconds: float = 600.0

    # A training_schedule row older than this (started_at) and still
    # is_completed=false is treated as stale rather than actually in
    # progress (see app/core/model_versions/training_schedule.py) —
    # self-heals from training-worker dying mid-run (container restart,
    # crash, OOM) without a manual DB fix. Well above any real training
    # run's duration (observed: well under 2 minutes for the current
    # dataset size) so it never cuts off a genuinely running job.
    training_schedule_stale_after_seconds: float = 1800.0

    # External Postgres holding the object_name -> label ground-truth
    # mapping used to train the captcha model (see
    # app/core/jobs/captcha_labels.py). Provisioned/maintained outside this
    # service; read-only from here. Discrete fields rather than a single
    # DATABASE_URL because the latter, as provisioned, omits user/password/
    # dbname inline (postgresql://postgres:@host:5432 with no db name) —
    # composed into a full URL by captcha_labels_database_url below.
    # Unprefixed validation_alias: these come from existing DB_* vars in
    # .env, not the app's usual AGENTIC_RPA_ prefix.
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=5432, validation_alias="DB_PORT")
    db_name: str = Field(default="postgres", validation_alias="DB_NAME")
    db_user: str = Field(default="postgres", validation_alias="DB_USER")
    db_password: str = Field(default="", validation_alias="DB_PASSWORD")
    db_ssl_mode: str = Field(default="disable", validation_alias="DB_SSL_MODE")

    @property
    def captcha_labels_database_url(self) -> str:
        """SQLAlchemy connection string for the captcha labels table, built
        from the discrete db_* fields above (see their comment for why).
        postgresql+psycopg:// selects the psycopg3 driver already in
        requirements.txt as SQLAlchemy's Postgres dialect implementation.
        """
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?sslmode={self.db_ssl_mode}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
