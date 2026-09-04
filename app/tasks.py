import asyncio
import tempfile
from pathlib import Path

from nodriver.core.connection import ProtocolException

from app.celery_app import celery_app
from app.core.config.config import get_settings
from app.core.jobs.captcha_store import save_captcha
from app.core.jobs.profile_store import load_profile
from app.core.logging.logging import get_logger

logger = get_logger(__name__)

# TODO: confirm against the real GST login form once available.
_LOGIN_LINK_SELECTOR = "a.button[href='govt/login']"
_USERNAME_SELECTOR = "#username"  # TODO: placeholder, confirm real selector
_PASSWORD_SELECTOR = "#password"  # TODO: placeholder, confirm real selector
_CAPTCHA_IMG_ID = "imgCaptcha"  # confirmed against the real GST login form
_CAPTCHA_IMG_SELECTOR = f"#{_CAPTCHA_IMG_ID}"
# _SUBMIT_SELECTOR: not used yet — the flow stops after capturing the captcha
# (submitting needs it solved first, see _gst_login's docstring). Add it back
# once the captcha-solving step exists and submit is wired up.

# --- Legacy PyAutoGUI/Xvfb/Tesseract RPA path -------------------------------
# Superseded by nodriver-based browser automation below: nodriver drives
# Chrome directly over CDP, so it doesn't need a virtual display, PyAutoGUI,
# or OCR just to interact with a web target. Left here, commented, as
# reference until the Xvfb/PyAutoGUI bits are fully removed from the image.
#
# import os
#
# from app.core.config.config import get_settings
#
#
# @celery_app.task(name="agentic_rpa.read_screen")
# def read_screen() -> dict:
#     """Grab a screenshot from the worker's virtual display and OCR it.
#
#     Placeholder action-grounding task: exercises the Xvfb + PyAutoGUI +
#     Tesseract path end-to-end. Real task logic (click/type/plan) still
#     needs the action-grounding schema called out in design.md.
#     """
#     os.environ.setdefault("DISPLAY", get_settings().display)
#
#     import pyautogui
#     import pytesseract
#
#     screenshot = pyautogui.screenshot()
#     text = pytesseract.image_to_string(screenshot)
#     return {"width": screenshot.width, "height": screenshot.height, "text": text}
# -----------------------------------------------------------------------------


async def _wait_for_image_loaded(page, element_id: str, *, timeout: float = 10.0, poll_interval: float = 0.5):
    """Poll until the given <img> element has actually finished loading.

    The captcha <img> (id=imgCaptcha) is AngularJS-bound: the element can
    exist in the DOM, matched by page.select(), well before Angular's
    data-ng-src binding has actually fetched and painted the image. A first
    attempt using a blind page.sleep() before screenshotting still produced
    a blank/degenerate 2x2 PNG — Element.save_screenshot() captures whatever
    is laid out *now*, and a size-0 image lays out as ~nothing. Poll the
    image's own naturalWidth (0 until the browser has decoded actual pixels)
    instead of guessing a fixed delay.
    """
    elapsed = 0.0
    while elapsed < timeout:
        natural_width = await page.evaluate(
            f"document.getElementById({element_id!r})?.naturalWidth || 0"
        )
        if natural_width and natural_width > 0:
            return
        await page.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError(f"Image #{element_id} did not finish loading within {timeout}s")


async def _wait_for_settled(page, selector: str, *, retries: int = 5, retry_delay: float = 1.0):
    """page.wait_for(), tolerant of a page mid-navigation.

    Right after a click that triggers navigation, CDP's underlying
    dom.get_document() call can briefly find no valid document (the old one
    is gone, the new one isn't ready) and raises ProtocolException("Could
    not find node with given id") — a real race, not a "selector not found
    yet" case, so wait_for's own retry loop doesn't cover it. Retry a few
    times with a short delay instead of guessing a single "long enough" sleep.
    """
    for attempt in range(retries):
        try:
            return await page.wait_for(selector)
        except ProtocolException:
            if attempt == retries - 1:
                raise
            await page.sleep(retry_delay)


async def _gst_login(task_id: str) -> dict:
    """Navigate to the GST portal, log in, and capture the captcha to MinIO.

    Flow: open the GST URL -> click the Login link -> fill username/password
    -> screenshot the captcha image element -> upload it to MinIO. Stops
    short of submitting the captcha itself (needs OCR/solving, not yet
    defined — see design.md) so the task's result is the captcha's MinIO
    object key for a human/downstream step to read and solve.
    """
    import nodriver as uc

    settings = get_settings()

    with load_profile() as profile_dir:
        # headless=False is deliberate for two reasons right now:
        #
        # 1. TEMPORARY: running headed (into the debug Xvfb display, see
        #    entrypoint.sh) so the automation can be watched live over VNC
        #    (localhost:5901) while GST selectors are being worked out.
        #    Once selectors are finalized, switch back to headless by adding
        #    browser_args=["--headless=new"] here (nodriver 0.45.2's own
        #    headless=True handshake is broken — see git history/PR notes —
        #    so headless mode must go through this raw Chromium arg, not
        #    the headless=True kwarg, even after debugging is done).
        #
        # sandbox=False -> passes --no-sandbox: the worker container runs as
        # root, and Chromium's setuid sandbox refuses to run as root without it.
        browser = await uc.start(
            user_data_dir=str(profile_dir),
            headless=False,
            sandbox=False,
        )
        try:
            page = await browser.get(settings.gst_url)

            login_link = await page.select(_LOGIN_LINK_SELECTOR)
            await login_link.click()
            await _wait_for_settled(page, _USERNAME_SELECTOR)

            username_field = await page.select(_USERNAME_SELECTOR)
            await username_field.send_keys(settings.gst_username)

            password_field = await page.select(_PASSWORD_SELECTOR)
            await password_field.send_keys(settings.gst_password)

            captcha_img = await page.select(_CAPTCHA_IMG_SELECTOR)
            await _wait_for_image_loaded(page, _CAPTCHA_IMG_ID)
            # Element.save_screenshot() writes a file and returns its path
            # (it has no in-memory/bytes mode) — capture to a temp file, read
            # it back, then discard the local file; only the MinIO copy persists.
            with tempfile.TemporaryDirectory() as tmp_dir:
                screenshot_path = Path(tmp_dir) / "captcha.png"
                await captcha_img.save_screenshot(filename=str(screenshot_path), format="png")
                captcha_bytes = screenshot_path.read_bytes()

            object_name = save_captcha(task_id, captcha_bytes)
        finally:
            # Browser.stop() is a plain sync method (not a coroutine) in
            # nodriver — awaiting it fails with "NoneType can't be used in
            # 'await' expression" and masks whatever error hit above it.
            browser.stop()

    return {"captcha_object": object_name}


@celery_app.task(name="agentic_rpa.gst_login", bind=True)
def gst_login(self) -> dict:
    return asyncio.run(_gst_login(self.request.id))
