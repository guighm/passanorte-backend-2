"""Best-effort recording of tourist access events (feature 014).

One dashboard-owned Starlette middleware (research R2): for every request
whose ``Authorization: Bearer`` carries a tourist JWT, appends one
``access_events`` row — including public endpoints consulted
authenticated (Q4 independent of route wiring). The recording is
best-effort (FR-022): any failure is a structured error log and the
tourist request is untouched; essential services never depend on this
subsystem. Staff tokens, forged/expired tokens and anonymous requests
record nothing (``peek_tourist_token``).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp

from passanorte_back.modules.auth.services.security import peek_tourist_token

logger = logging.getLogger("passanorte.dashboard")


@contextmanager
def _open_session() -> Iterator[Session]:
    """Session factory for the ledger (own transaction — production engine).

    Module-level indirection so tests can point the recording at the
    isolated engine (conftest) without touching the auth hot path.
    """
    from passanorte_back.core.db import sessionfactory

    with sessionfactory() as session:
        yield session


def record_access(tourist_id: int) -> None:
    """Append one access event — failures never propagate (FR-022)."""
    from passanorte_back.modules.dashboard.repositories.access_events import (
        add_access_event,
    )

    try:
        with _open_session() as session:
            add_access_event(session, tourist_id=tourist_id)
            session.commit()
    except Exception:  # noqa: BLE001 — best-effort observability
        logger.exception("failed to record the tourist access event (tourist=%s)", tourist_id)


def register_access_recording(app: FastAPI) -> None:
    """Mount the recording middleware on the composition root (main.py)."""

    class AccessRecordingMiddleware(BaseHTTPMiddleware):
        """Record one event per tourist-authenticated request."""

        def __init__(self, asgi_app: ASGIApp) -> None:
            super().__init__(asgi_app)

        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
            response = await call_next(request)  # noqa: ANN202 — BaseHTTPMiddleware
            authorization = request.headers.get("Authorization", "")
            token = authorization.removeprefix("Bearer ").strip()
            tourist_id = peek_tourist_token(token) if token else None
            if tourist_id is not None:
                record_access(tourist_id)
            return response

    app.add_middleware(AccessRecordingMiddleware)
