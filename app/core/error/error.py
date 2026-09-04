from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging.logging import get_logger
from app.core.response import ServiceStatus

logger = get_logger(__name__)

_CODE_BY_STATUS = {
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
}

_HTTP_STATUS_BY_SERVICE_STATUS = {
    ServiceStatus.NOT_FOUND: status.HTTP_404_NOT_FOUND,
}


def raise_for_status(service_status: ServiceStatus) -> None:
    if service_status != ServiceStatus.SUCCESS:
        raise HTTPException(
            status_code=_HTTP_STATUS_BY_SERVICE_STATUS[service_status],
            detail=service_status.value,
        )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _CODE_BY_STATUS.get(exc.status_code, "http_error")
    return _error_response(exc.status_code, code, str(exc.detail))


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error", str(exc.errors())
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_server_error", "Internal server error"
    )


def setup_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
