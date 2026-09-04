FROM python:3.12-alpine

# System deps:
# - xvfb + xauth: virtual framebuffer so PyAutoGUI has a display to render to
# - x11vnc: bridges the Xvfb display to VNC so a viewer (e.g. TightVNC) can watch it live
# - xterm + xsetroot: no RPA app yet — just draws something on the otherwise
#   blank Xvfb screen so a VNC viewer has visible proof of life
# - chromium: Alpine has no Google Chrome package (glibc-only .deb, Alpine is
#   musl) — Chromium is the same engine/UI family and installs natively here
# - tesseract-ocr + tesseract-ocr-data-eng: OCR engine behind pytesseract, plus
#   the English trained-language data (the engine package alone ships no languages)
# - scrot: screenshot backend PyAutoGUI shells out to on Linux
# - gcc/musl-dev/etc: build deps for wheels without musllinux builds (e.g. pillow, pyautogui deps)
# - the gdk-pixbuf/gtk/x11 libs: runtime deps for python3-xlib / pyscreeze image handling
RUN apk add --no-cache \
        xvfb \
        xauth \
        xdpyinfo \
        x11vnc \
        xterm \
        setxkbmap \
        xsetroot \
        chromium \
        tesseract-ocr \
        tesseract-ocr-data-eng \
        scrot \
        python3-tkinter \
        gtk+3.0 \
        gdk-pixbuf \
        libx11 \
        libxext \
        libxtst \
        libxrandr \
        ttf-dejavu \
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

ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1 \
    XDG_SESSION_TYPE=x11
# XDG_SESSION_TYPE=x11 isn't set automatically by Xvfb (only a real desktop
# session manager sets it) — but pyscreeze's Linux backend gates its scrot
# fallback on RUNNING_X11, which it derives from this var. Without it,
# pyautogui.screenshot() falls through to "install gnome-screenshot" even
# though scrot is installed and Xvfb is in fact an X11 display.

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
