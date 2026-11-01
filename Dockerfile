# syntax=docker/dockerfile:1

# Multi-stage build (spec 004 FR-001..FR-004; research D1-D5):
#   build stage  — uv syncs dependencies strictly from pyproject.toml + uv.lock
#   runtime stage— slim image, non-root user, no build toolchain, no secrets

# ==== Build stage ====
FROM python:3.13-slim AS build

# Pin uv to the minor version that produced uv.lock (research D1 — never "latest").
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

# copy link mode keeps the venv relocatable; bytecode is built on the host-free
# runtime import path anyway. Keep defaults light for a slim result.
ENV UV_LINK_MODE=copy

WORKDIR /app

# Sync dependencies first for layer caching: the lockfile layer survives code
# changes. --no-install-project skips building the project itself (its sources
# are not copied yet at this layer).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application files (build context cleaned by .dockerignore)
# README.md is needed: package metadata (pyproject `readme = "README.md"`).
COPY README.md /app/README.md
COPY src/ /app/src/
COPY config/ /app/config/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

# Install the project itself on top of the cached dependency layer (editable
# install inside the venv, which is how hot reload research D4 works).
RUN uv sync --frozen --no-dev

# ==== Runtime stage ====
FROM python:3.13-slim AS runtime

# Receive the synced environment and application files from the build stage.
COPY --from=build /app /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Non-root user (FR-002 / constitution Principle II)
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Entrypoint runs `alembic upgrade head` then execs the CMD (or a compose
# `command:` override — research D3/D4).
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "passanorte_back.main:app", "--host", "0.0.0.0", "--port", "8000"]