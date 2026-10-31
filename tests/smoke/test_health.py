"""Smoke: contrato GET /health (contracts/health.md, FR-009, clarificação Q1).

200 {status: ok, database: ok} com banco conectado; 503
{status: degraded, database: unavailable} quando o ping do banco falha.
Ambos em < 1 s (SC-002).
"""

import importlib
import time

import pytest
from fastapi.testclient import TestClient

from passanorte_back.main import app

# ``passanorte_back`` re-exporta a função ``main`` (script uv), sombreando o
# submódulo como atributo do pacote — import_module resolve o módulo real.
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
