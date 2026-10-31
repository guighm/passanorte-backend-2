"""Smoke: app lifespan (plan.md ``main.py`` "ciclo de vida" touch-point).

Entering the lifespan starts normally; leaving it disposes the DB engine
exactly once — no leaked connections on shutdown.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

# ``passanorte_back.__init__`` re-exports the ``main`` function (uv script),
# shadowing the subpackage as a package attribute — import_module resolves
# the real module under the full name.
main = importlib.import_module("passanorte_back.main")


class _DisposableEngine:
    def __init__(self) -> None:
        self.dispose_calls = 0

    def dispose(self) -> None:
        self.dispose_calls += 1


def test_lifespan_disposes_engine_exactly_once_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_engine = _DisposableEngine()
    monkeypatch.setattr(main, "engine", fake_engine, raising=False)

    assert fake_engine.dispose_calls == 0
    with TestClient(main.app):
        assert fake_engine.dispose_calls == 0  # nothing disposed at startup
    assert fake_engine.dispose_calls == 1  # disposed once on shutdown


def test_app_registry_uses_lifespan() -> None:
    assert main.app.router.lifespan_context is not None
