#!/bin/sh
set -e

# TEMPORARY debug aid: Xvfb + x11vnc so the GST automation (app/tasks.py) can
# be watched live over VNC while its selectors are being worked out against
# the real site. nodriver normally drives Chromium fully headless over CDP
# and needs none of this — once selectors are finalized, drop this whole
# block, the "worker" case's x11vnc line below, and go back to headless
# (browser_args=["--headless=new"]) in app/tasks.py.
start_debug_display() {
    DISPLAY_NUM="${DISPLAY#:}"
    # Clear any stale lock/socket left behind by an unclean shutdown —
    # otherwise Xvfb refuses to bind and this would silently run with no display.
    rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"

    Xvfb "$DISPLAY" -screen 0 1920x1080x24 &
    XVFB_PID=$!

    cleanup() {
        kill "$XVFB_PID" 2>/dev/null || true
    }
    trap cleanup EXIT INT TERM

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

    # No -auth cookie is used, so no Xauthority is strictly required — but
    # python-xlib (a nodriver/CDP-adjacent dep) errors out if the file is
    # simply missing rather than treating "no file" as "no auth needed".
    touch /root/.Xauthority

    # Bridge the Xvfb display to VNC — connect a viewer (e.g. TightVNC) to
    # localhost:5901 (see docker-compose.yml) to watch Chromium live.
    x11vnc -display "$DISPLAY" -forever -shared -nopw -quiet &
}

case "$1" in
    api)
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    worker)
        start_debug_display
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
