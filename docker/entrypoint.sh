#!/bin/sh
set -e

# TEMPORARY debug aid: Xvfb + x11vnc so the GST automation
# (app/tasks/rpa_tasks.py) can be watched live over VNC while its selectors
# are being worked out against the real site. nodriver normally drives
# Chromium fully headless over CDP and needs none of this — once selectors
# are finalized, drop this whole block, the "worker" case's x11vnc line
# below, and go back to headless (browser_args=["--headless=new"]) in
# app/tasks/rpa_tasks.py.
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
        # --include app.tasks.rpa_tasks: this is the only worker command that
        # imports rpa_tasks.py (nodriver/Chromium) — training_tasks.py
        # (torch) is never loaded here. -Q rpa: only consumes tasks routed
        # to the "rpa" queue (see app/celery_app.py's task_routes).
        start_debug_display
        exec celery -A app.celery_app.celery_app worker \
            --include app.tasks.rpa_tasks \
            -Q rpa \
            --loglevel=info
        ;;
    training-worker)
        # No start_debug_display: this worker never touches a browser, so it
        # needs no Xvfb/x11vnc (and Dockerfile.training doesn't install
        # them). --include/-Q mirror the "worker" case's role-scoping, for
        # training_tasks.py (torch) and the "training" queue instead.
        exec celery -A app.celery_app.celery_app worker \
            --include app.tasks.training_tasks \
            -Q training \
            --loglevel=info
        ;;
    predict-worker)
        # No start_debug_display, same reasoning as training-worker.
        # --include/-Q scope this process to predict_tasks.py (torch, no
        # mlflow) and the "predict" queue — a separate worker from
        # training-worker so interactive predictions never queue behind a
        # long training run.
        exec celery -A app.celery_app.celery_app worker \
            --include app.tasks.predict_tasks \
            -Q predict \
            --loglevel=info
        ;;
    validator-worker)
        # No start_debug_display, same reasoning as training-worker/
        # predict-worker. --include/-Q scope this process to
        # validator_tasks.py (requests + Postgres, no torch) and the
        # "validate" queue — enqueued automatically by train_captcha_model
        # on success, not on its own schedule.
        exec celery -A app.celery_app.celery_app worker \
            --include app.tasks.validator_tasks \
            -Q validate \
            --loglevel=info
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
