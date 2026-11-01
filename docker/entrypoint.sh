#!/usr/bin/env bash
# Container entrypoint (spec 004 FR-008/v, research D3): run database
# migrations, then `exec "$@"` — the image CMD by default, or a compose
# `command:` override (e.g. uvicorn --reload in the dev environment).
# A migration failure exits non-zero so the container never serves traffic
# over a broken schema (spec 004 edge cases).
set -e

alembic upgrade head

# Hand PID 1 to the requested command (clean SIGTERM on docker stop).
exec "$@"