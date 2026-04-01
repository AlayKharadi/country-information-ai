# ------------------------------------------------------------
# Builder stage: install dependencies
# Must use the same base as the runtime stage (both Alpine)
# so native extensions compiled here run there without issues.
# ------------------------------------------------------------
FROM python:3.14-alpine3.21 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON=3.14 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_SYSTEM_PYTHON=1

# gcc / musl-dev / libffi-dev are needed to compile any C-extension packages.
RUN apk add --no-cache gcc musl-dev libffi-dev

# Copy uv from the official image rather than curl-installing it.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first so this layer is cached on code-only changes.
COPY pyproject.toml uv.lock ./

# --no-dev keeps dev tooling out of the image; --locked pins to uv.lock exactly.
RUN uv sync --locked --no-dev

# Copy application code after deps (code changes don't bust the dep cache).
COPY app/ ./app/

# ------------------------------------------------------------
# Runtime stage: minimal image for execution
# ------------------------------------------------------------
FROM python:3.14-alpine3.21 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Cloud Run injects PORT; default matches Cloud Run's expectation.
    PORT=8080

# libffi is the only runtime-only shared lib needed post-install.
RUN apk add --no-cache libffi

# Non-root user for least-privilege execution.
RUN adduser -D -s /bin/sh appuser

WORKDIR /app

# uv sync installs into /app/.venv — copy that, not system site-packages.
COPY --from=builder /app/.venv /app/.venv

# Application code only — no pyproject.toml, uv.lock, or tooling.
COPY --from=builder /app/app ./app/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

