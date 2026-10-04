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
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency definition
COPY pyproject.toml ./

# Install dependencies
RUN uv lock && uv sync --no-dev

# Copy application source
COPY . .

# Give application user ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 7877

CMD [".venv/bin/python", "main.py"]