from fastapi import FastAPI

from app.api.v1.captcha_label_api import router as captcha_label_router
from app.api.v1.health_api import router as health_router
from app.api.v1.job_api import router as job_router
from app.api.v1.label_ui import router as label_ui_router
from app.core.config.config import get_settings
from app.core.error.error import setup_error_handlers
from app.core.logging.logging import setup_logging

setup_logging()

settings = get_settings()

app = FastAPI(title=settings.app_name)

setup_error_handlers(app)

app.include_router(health_router, prefix="/api/v1")
app.include_router(job_router, prefix="/api/v1")
app.include_router(captcha_label_router, prefix="/api/v1")
app.include_router(label_ui_router)
