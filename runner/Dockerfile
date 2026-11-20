# Runner image (Story 1.2, AD-19). Built from the repository root:
#   docker compose build runner   (context ".", dockerfile runner/Dockerfile)
# The image tag always equals the pinned Playwright version.
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

# Virtual display + VNC + noVNC (browser view on :6080), and venv support.
# The base image points apt at azure.archive.ubuntu.com, which can be very slow
# outside Azure (~50 KB/s measured); use the main Ubuntu archive instead.
RUN sed -i 's|http://azure.archive.ubuntu.com|http://archive.ubuntu.com|g' \
      /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf vnc.html /usr/share/novnc/index.html

# Python dependencies in their own venv so they never clash with Ubuntu's python3-* packages.
# Browsers come from the base image (/ms-playwright), which matches playwright==1.65.2.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY contracts/ /opt/contracts/
RUN python3 -m venv /opt/venv \
 && pip install --no-cache-dir \
      playwright==1.65.2 \
      pytest-playwright==0.10.0 \
      fastapi==0.165.0 \
      pydantic==2.14.4 \
      uvicorn==0.54.0 \
      sse-starlette==3.7.0 \
      /opt/contracts

WORKDIR /opt/runner
COPY runner/app app
COPY runner/entrypoint.sh /usr/local/bin/runner-entrypoint
# /exchange is the shared volume mount point; open to the (non-root) runtime user.
RUN chmod 755 /usr/local/bin/runner-entrypoint \
 && mkdir -p /exchange && chmod 1777 /exchange

ENV DISPLAY=:99 \
    HOME=/tmp/home \
    EXCHANGE_DIR=/exchange \
    RUNNER_HEADLESS=false

# Non-root. docker-compose overrides the uid/gid with the host user's (like the
# backend) so both containers own the exchange files they share.
USER pwuser

EXPOSE 8100 6080
ENTRYPOINT ["/usr/local/bin/runner-entrypoint"]
