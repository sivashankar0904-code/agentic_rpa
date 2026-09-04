from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Shared config for the API and Celery worker, sourced from env vars."""

    model_config = SettingsConfigDict(env_prefix="AGENTIC_RPA_", extra="ignore")

    app_name: str = "agentic_rpa"
    log_level: str = "INFO"

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    display: str = ":99"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
