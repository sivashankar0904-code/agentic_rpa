"""Server-rendered htmx UI for manually labeling captured captchas.

Not a JSON API — mounted at /label (unversioned, unlike the /api/v1/*
routers) since this is a browser page, not a programmatic contract. Reuses
the same captcha_label_service business layer as
app/api/v1/captcha_label_api.py; this module only adds HTML rendering
(Jinja2 templates under app/templates/) and an htmx-friendly form-post
endpoint on top of it.
"""

from fastapi import APIRouter, Form, Request, Response
from fastapi.templating import Jinja2Templates

from app.core.captcha_labels import captcha_label_service
from app.core.response import ServiceStatus

router = APIRouter(prefix="/label", tags=["label-ui"], include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=Response)
def label_page(request: Request) -> Response:
    """Full page: every unsolved captcha, each with an image + save form."""
    response = captcha_label_service.list_unsolved_captchas()
    captchas = response.data if response.status == ServiceStatus.SUCCESS else []
    return templates.TemplateResponse(
        request=request, name="label.html", context={"captchas": captchas}
    )


@router.get("/{object_name}/image", response_class=Response)
def label_captcha_image(object_name: str) -> Response:
    """Same image bytes as the JSON API's endpoint — kept separate so this
    UI's <img> tags don't depend on /api/v1 staying unversioned/unchanged."""
    response = captcha_label_service.get_captcha_image(object_name)
    if response.status != ServiceStatus.SUCCESS:
        return Response(status_code=404)
    return Response(content=response.data, media_type="image/png")


@router.post("/{object_name}/solve", response_class=Response)
def label_solve_captcha(request: Request, object_name: str, label: str = Form(...)) -> Response:
    """htmx form target: saves the label, returns the row's replacement HTML.

    Success removes the row from the DOM (nothing left to label); failure
    re-renders the row in place with an error message instead of losing the
    text the user just typed.
    """
    response = captcha_label_service.solve_captcha(object_name, label)
    if response.status != ServiceStatus.SUCCESS:
        return templates.TemplateResponse(
            request=request,
            name="_captcha_row_error.html",
            context={"object_name": object_name, "error": "Could not save — try again."},
        )
    return Response(content="", media_type="text/html")
