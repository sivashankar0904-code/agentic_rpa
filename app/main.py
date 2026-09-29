from fastapi import FastAPI

from app.api.v1.example_api import router as example_router
from app.core.config.config import get_settings
from app.core.error.error import setup_error_handlers
from app.core.logging.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(title=settings.app_name)

setup_error_handlers(app)

app.include_router(example_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
