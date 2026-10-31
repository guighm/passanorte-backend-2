"""Smoke: GET /health contract (contracts/health.md, FR-009, clarification Q1).

200 {status: ok, database: ok} with a connected database; 503
{status: degraded, database: unavailable} when the database ping fails.
Both under 1 s (SC-002).
"""

import importlib
import time

import pytest
from fastapi.testclient import TestClient

from passanorte_back.main import app

# ``passanorte_back.__init__`` re-exports the ``main`` function (uv script),
# shadowing the subpackage as a package attribute — import_module resolves
# the real module under the full name.
main_module = importlib.import_module("passanorte_back.main")

client = TestClient(app)


def test_health_healthy_returns_200_ok() -> None:
    start = time.perf_counter()
    response = client.get("/health")
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert elapsed < 1.0  # SC-002


def test_health_degraded_returns_503_when_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "ping_database", lambda _engine: False)

    start = time.perf_counter()
    response = client.get("/health")
    elapsed = time.perf_counter() - start

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
    assert elapsed < 1.0  # SC-002
