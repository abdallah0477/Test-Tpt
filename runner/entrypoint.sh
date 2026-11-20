#!/bin/sh
# Start the virtual display, VNC, noVNC, then the Runner API (AD-19).
# The root filesystem is read-only: everything writable lives in /tmp (tmpfs).
set -e

mkdir -p "$HOME"

Xvfb :99 -screen 0 1400x1000x24 -nolisten tcp &
# Wait until the X server socket exists before anything connects to it.
i=0
while [ ! -e /tmp/.X11-unix/X99 ] && [ $i -lt 100 ]; do i=$((i + 1)); sleep 0.1; done

# VNC server on localhost only; noVNC (websockify) is the only way in, on :6080.
x11vnc -display :99 -rfbport 5900 -localhost -forever -shared -nopw -quiet -noxdamage &
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

cd /opt/runner
exec uvicorn app.api:app --host 0.0.0.0 --port 8100 --workers 1
