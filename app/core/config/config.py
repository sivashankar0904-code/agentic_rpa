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


@lru_cache
def get_settings() -> Settings:
    return Settings()
