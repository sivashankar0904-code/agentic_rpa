from fastapi import APIRouter, Response

from app.core.captcha_labels import captcha_label_service
from app.core.error.error import raise_for_status
from app.schemas.captcha_label_schema import (
    CaptchaLabelRead,
    CaptchaLabelSolveRequest,
    CaptchaPredictionRead,
)

router = APIRouter(prefix="/captcha-labels", tags=["captcha-labels"])


@router.get(
    "/unsolved",
    response_model=list[CaptchaLabelRead],
    operation_id="listUnsolvedCaptchas",
    summary="List captured captchas still awaiting a manual label",
)
def list_unsolved_captchas() -> list[CaptchaLabelRead]:
    """List every captcha_labels row not yet solved, oldest first."""
    response = captcha_label_service.list_unsolved_captchas()
    raise_for_status(response.status)
    return response.data


@router.post(
    "/{object_name}/solve",
    response_model=CaptchaLabelRead,
    operation_id="solveCaptcha",
    summary="Record a manually-entered label for a captured captcha",
)
def solve_captcha(object_name: str, request: CaptchaLabelSolveRequest) -> CaptchaLabelRead:
    """Set a captcha's ground-truth label and mark it solved."""
    response = captcha_label_service.solve_captcha(object_name, request.label)
    raise_for_status(response.status)
    return response.data


@router.get(
    "/{object_name}/image",
    operation_id="getCaptchaImage",
    summary="Fetch a captured captcha's raw PNG bytes",
    response_class=Response,
)
def get_captcha_image(object_name: str) -> Response:
    """Stream a captcha's image from MinIO — used by the /label UI's <img>."""
    response = captcha_label_service.get_captcha_image(object_name)
    raise_for_status(response.status)
    return Response(content=response.data, media_type="image/png")


@router.post(
    "/{object_name}/predict",
    response_model=CaptchaPredictionRead,
    operation_id="predictCaptcha",
    summary="Predict a captured captcha's text using the current trained model",
)
def predict_captcha(object_name: str) -> CaptchaPredictionRead:
    """Run predict-worker's current model against one captcha and return its guess."""
    response = captcha_label_service.predict_captcha(object_name)
    raise_for_status(response.status)
    return response.data
