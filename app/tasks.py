import os

from app.celery_app import celery_app
from app.core.config.config import get_settings


@celery_app.task(name="agentic_rpa.read_screen")
def read_screen() -> dict:
    """Grab a screenshot from the worker's virtual display and OCR it.

    Placeholder action-grounding task: exercises the Xvfb + PyAutoGUI +
    Tesseract path end-to-end. Real task logic (click/type/plan) still
    needs the action-grounding schema called out in design.md.
    """
    os.environ.setdefault("DISPLAY", get_settings().display)

    import pyautogui
    import pytesseract

    screenshot = pyautogui.screenshot()
    text = pytesseract.image_to_string(screenshot)
    return {"width": screenshot.width, "height": screenshot.height, "text": text}
