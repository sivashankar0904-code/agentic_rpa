#!/bin/sh
set -e

# Start a virtual framebuffer so PyAutoGUI/Tesseract-driven automation has a
# display to render to. Each container gets its own DISPLAY (:99 by default);
# scale worker isolation (design.md gap #4) by overriding DISPLAY per replica.
#
# Clear any stale lock/socket left behind by an unclean shutdown (e.g. a
# killed container reusing the same /tmp) — otherwise Xvfb refuses to bind
# and this script would silently carry on with no display.
DISPLAY_NUM="${DISPLAY#:}"
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"

Xvfb "$DISPLAY" -screen 0 1920x1080x24 &
XVFB_PID=$!

cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Give Xvfb a moment to bind before anything tries to connect to $DISPLAY.
ready=0
for _ in $(seq 1 10); do
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        break
    fi
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 0.5
done

if [ "$ready" -ne 1 ]; then
    echo "Xvfb failed to start on display $DISPLAY" >&2
    exit 1
fi

# Xvfb here runs with no -auth cookie, so no Xauthority is actually required —
# but python-xlib (pulled in by pyautogui/mouseinfo) errors out if the file is
# simply missing rather than treating "no file" as "no auth needed". An empty
# file satisfies that check without adding real auth.
touch /root/.Xauthority

case "$1" in
    api)
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    worker)
        # Bridge the Xvfb display to VNC so a viewer (e.g. TightVNC) can watch
        # PyAutoGUI drive the screen live. -forever keeps serving past a
        # client disconnect; -shared allows more than one viewer at once.
        x11vnc -display "$DISPLAY" -forever -shared -nopw -quiet &

        # No real RPA target yet (design.md gap #2) — paint the background and
        # open a browser so the display isn't just black in a VNC viewer.
        # --no-sandbox: Chromium's setuid/namespace sandbox needs privileges
        # this container doesn't have; running as root here anyway (see the
        # Celery superuser warning in the worker logs), so it buys nothing.
        # --no-first-run/--no-default-browser-check/--disable-sync/
        # --disable-features=ChromeSigninClientCore: this is a disposable,
        # unauthenticated profile — without these, Chromium opens a stray
        # accounts.google.com sync tab on startup that 400s and has nothing
        # to do with whatever page we actually navigate to.
        xsetroot -solid "#2b2b2b" -display "$DISPLAY" 2>/dev/null || true
        chromium \
            --no-sandbox \
            --disable-gpu \
            --window-size=1920,1080 \
            --window-position=0,0 \
            --user-data-dir=/tmp/chromium-profile \
            --no-first-run \
            --no-default-browser-check \
            --disable-sync \
            --disable-features=ChromeSigninClientCore \
            "https://www.google.com" \
            --display="$DISPLAY" &

        exec celery -A app.celery_app.celery_app worker --loglevel=info
        ;;
    beat)
        exec celery -A app.celery_app.celery_app beat --loglevel=info
        ;;
    flower)
        exec celery -A app.celery_app.celery_app flower --port=5555
        ;;
    *)
        exec "$@"
        ;;
esac
