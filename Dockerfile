FROM python:3.12-alpine

# System deps:
# - chromium: Alpine has no Google Chrome package (glibc-only .deb, Alpine is
#   musl) — Chromium is the same engine/UI family and installs natively here.
#   Driven directly over CDP by nodriver (see app/tasks.py).
# - ttf-dejavu: fonts so pages render text instead of tofu boxes.
# - xvfb + xauth + xdpyinfo + x11vnc: TEMPORARY debug aid so the GST
#   automation can be watched live over VNC while selectors are being worked
#   out against the real site (xdpyinfo is entrypoint.sh's Xvfb readiness
#   check, not needed for anything else). nodriver normally runs fully
#   headless and needs none of this — remove these packages, the DISPLAY env
#   below, and the worker's Xvfb/x11vnc bring-up in entrypoint.sh once
#   selectors are finalized.
#
# The old xterm/tesseract/scrot/gtk/x11-lib block that used to live here
# supported the legacy PyAutoGUI RPA path (commented out in app/tasks.py)
# and stays gone — only re-adding the minimum needed for VNC debugging.
RUN apk add --no-cache \
        chromium \
        ttf-dejavu \
        xvfb \
        xauth \
        xdpyinfo \
        x11vnc \
    && apk add --no-cache --virtual .build-deps \
        gcc \
        musl-dev \
        jpeg-dev \
        zlib-dev

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99
# DISPLAY: TEMPORARY, for the debug Xvfb/x11vnc bring-up in entrypoint.sh
# (worker only) — drop once VNC debugging is no longer needed.

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
