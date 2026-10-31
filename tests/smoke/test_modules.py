"""Smoke: modules registered under /api/v1 (contracts/module-routers.md).

Empty routers generate no OpenAPI paths — the check runs against the
mounted routers (central registry ``core.routers`` + effective mounting
with probes), not against paths. ``/health`` and ``/docs`` live outside
the prefix.
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from passanorte_back.core import routers as routers_registry
from passanorte_back.main import app

client = TestClient(app)

EXPECTED_MODULES = [
    "auth",
    "employees",
    "tourists",
    "tourist_spots",
    "events",
    "gamification",
    "visitation",
    "dashboard",
    "notifications",
    "chatbot",
]


def test_app_boots_without_error() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_registry_contains_all_ten_modules_in_stable_order() -> None:
    assert list(routers_registry.MODULE_ROUTERS) == EXPECTED_MODULES


def test_each_router_has_module_prefix_with_hyphens() -> None:
    for name in EXPECTED_MODULES:
        router = routers_registry.MODULE_ROUTERS[name]
        assert router.prefix == f"/api/v1/{name.replace('_', '-')}"


def test_register_routers_mounts_every_module_under_api_v1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Effective mounting: probes with 1 temporary route go through
    ``register_routers`` — the same ``include_router`` path used in
    production — and become reachable at ``/api/v1/<module>``.
    """
    fresh_app = FastAPI()
    probe_routers: dict[str, APIRouter] = {}
    for name in EXPECTED_MODULES:
        router = APIRouter(prefix=routers_registry.module_prefix(name))
        router.get("")(lambda name=name: {"module": name})  # type: ignore[arg-type]
        probe_routers[name] = router
    monkeypatch.setattr(routers_registry, "MODULE_ROUTERS", probe_routers)

    routers_registry.register_routers(fresh_app)
    probe_client = TestClient(fresh_app)

    for name in EXPECTED_MODULES:
        expected_path = f"/api/v1/{name.replace('_', '-')}"
        response = probe_client.get(expected_path)
        assert response.status_code == 200, f"module {name} missing path {expected_path}"


def test_health_and_docs_live_outside_api_v1_prefix() -> None:
    api_v1_prefix = "/api/v1/"
    for route in app.routes:
        path = getattr(route, "path", "")
        if path == "/health" or path.startswith(("/docs", "/openapi.json", "/redoc")):
            assert not path.startswith(api_v1_prefix)
    openapi_paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in openapi_paths
    for path in openapi_paths:
        assert path == "/health" or path.startswith(api_v1_prefix)
