# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.14.3

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /app

ARG UID=10001

RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project dependency definition
COPY pyproject.toml ./

# Generate lock file and install dependencies
RUN uv lock && uv sync --no-dev

# Copy application source
COPY . .

# Give application user ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 7877

CMD ["uv", "run", "python", "main.py"]