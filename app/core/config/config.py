from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "agentic-rpa"

    db_host: str
    db_port: int = 5432
    db_user: str
    db_password: str
    db_name: str
    db_ssl_mode: str = "disable"


@lru_cache
def get_settings() -> Settings:
    return Settings()
