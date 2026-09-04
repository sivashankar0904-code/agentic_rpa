FROM python:3.12-alpine

# uv: static binary, copied in rather than pip-installed — same mechanism on
# this Alpine image and Dockerfile.training's Debian one. Faster installs
# than pip and more reliable on large wheels (retries/resumable downloads),
# which matters for Dockerfile.training's torch install in particular.
COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv /usr/local/bin/uv

# RPA image: api, rpa-worker, beat, flower all build from this Dockerfile.
# Training runs in a separate image (Dockerfile.training, python:3.12-slim)
# because torch has no musl-compatible wheel or sdist — Alpine has nothing
# to install it from at all. Keeping this image on Alpine (rather than
# moving everything to slim) keeps the RPA-only services small, since none
# of them need torch.
#
# System deps:
# - chromium: Alpine has no Google Chrome package (glibc-only .deb, Alpine is
#   musl) — Chromium is the same engine/UI family and installs natively here.
#   Driven directly over CDP by nodriver (see app/tasks/rpa_tasks.py).
# - ttf-dejavu: fonts so pages render text instead of tofu boxes.
# - xvfb + xauth + xdpyinfo + x11vnc: TEMPORARY debug aid so the GST
#   automation can be watched live over VNC while selectors are being worked
#   out against the real site (xdpyinfo is entrypoint.sh's Xvfb readiness
#   check, not needed for anything else). nodriver normally runs fully
#   headless and needs none of this — remove these packages, the DISPLAY env
#   below, and the rpa-worker's Xvfb/x11vnc bring-up in entrypoint.sh once
#   selectors are finalized. Not present in Dockerfile.training at all —
#   the training worker never touches a browser.
#
# The old xterm/tesseract/scrot/gtk/x11-lib block that used to live here
# supported the legacy PyAutoGUI RPA path (commented out in
# app/tasks/rpa_tasks.py) and stays gone — only re-adding the minimum needed
# for VNC debugging.
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
RUN uv pip install --system --no-cache -r requirements.txt \
    && apk del .build-deps

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99
# DISPLAY: TEMPORARY, for the debug Xvfb/x11vnc bring-up in entrypoint.sh
# (rpa-worker only) — drop once VNC debugging is no longer needed.

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
