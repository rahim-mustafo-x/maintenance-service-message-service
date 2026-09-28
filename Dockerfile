# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.14.3

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ARG UID=10001

RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency definitions and lock file
COPY pyproject.toml uv.lock ./

# Install dependencies from the lock file
RUN uv sync --locked --no-dev

# Copy application source
COPY . .

# Give application user ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 7877

CMD ["uv", "run", "python", "main.py"]