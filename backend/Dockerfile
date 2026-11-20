# Built from the repository root: docker compose builds it with context "."
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Shared contracts package first, then locked dependencies (cached layer)
COPY contracts/ contracts/
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev

COPY backend/app backend/app
COPY config.toml .

ENV CONFIG_PATH=/app/config.toml \
    DATA_DIR=/app/data

WORKDIR /app/backend
EXPOSE 8000

# One worker only: store.py relies on in-process locks (AD-4)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
