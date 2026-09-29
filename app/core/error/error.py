from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.response import ServiceStatus

_STATUS_TO_HTTP = {
    ServiceStatus.NOT_FOUND: 404,
    ServiceStatus.CONFLICT: 409,
    ServiceStatus.UNAUTHORIZED: 401,
}


def raise_for_status(status: ServiceStatus) -> None:
    if status == ServiceStatus.SUCCESS:
        return
    code = _STATUS_TO_HTTP.get(status, 400)
    raise HTTPException(status_code=code, detail=status.value)


def setup_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": str(exc.detail)}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": 500, "message": "internal server error"}},
        )
