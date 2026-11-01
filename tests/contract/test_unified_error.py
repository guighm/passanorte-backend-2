"""Contract: unified error payload (spec 005 FR-005 / clarification Q1).

A probe app wires ``core.error_handlers`` — the single ``ApiError`` shape
must hold for every failure path: validation 422 (names the received key),
HTTPException taxonomy, 500 generic (never leaks internals).
"""

from unittest.mock import ANY

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from passanorte_back.core.error_handlers import register_error_handlers
from passanorte_back.core.schemas import ApiModel

ERROR_KEYS = {"errorCode", "message", "details"}


def build_probe_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    class _ProbeRequest(ApiModel):
        first_name: str

    @app.post("/probe")
    def probe(data: _ProbeRequest) -> dict[str, str]:
        return {"receivedFirstName": data.first_name}

    @app.get("/gone")
    def gone():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="no such thing")

    @app.get("/boom")
    def boom():
        raise RuntimeError("internal secret must not leak")

    return app


@pytest.fixture
def probe_client() -> TestClient:
    # server exceptions surfaced as 500 responses (no re-raise) for /boom
    return TestClient(build_probe_app(), raise_server_exceptions=False)


def test_unhandled_exception_is_500_internal_error_generic(probe_client: TestClient) -> None:
    response = probe_client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["errorCode"] == "internal_error"
    assert "internal secret" not in body["message"]


def test_http_exception_maps_status_to_camel_case_error(probe_client: TestClient) -> None:
    response = probe_client.get("/gone")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["errorCode"] == "resource_not_found"
    assert body["message"] == "no such thing"
    assert body["details"] == []


def test_camel_case_input_is_accepted(probe_client: TestClient) -> None:
    response = probe_client.post("/probe", json={"firstName": "Ana"})
    assert response.status_code == 200
    assert response.json() == {"receivedFirstName": "Ana"}


def _assert_validation_shape(response) -> list[dict[str, str]]:
    body = response.json()
    assert response.status_code == 422
    assert set(body) == ERROR_KEYS
    assert body["errorCode"] == "validation_error"
    assert body["message"]
    return body["details"]


def test_snake_case_input_names_received_key_in_details(probe_client: TestClient) -> None:
    details = _assert_validation_shape(probe_client.post("/probe", json={"first_name": "Ana"}))
    keys = [item["key"] for item in details]
    assert "first_name" in keys  # the offending key AS RECEIVED (value-exempt)
    offending = next(item for item in details if item["key"] == "first_name")
    assert set(offending) == {"key", "message"}
    assert offending["message"]


def test_unknown_input_key_named_in_422(probe_client: TestClient) -> None:
    details = _assert_validation_shape(
        probe_client.post("/probe", json={"firstName": "Ana", "unknownKey": "z"})
    )
    assert {"key": "unknownKey", "message": ANY} in details


def test_missing_required_key_is_422(probe_client: TestClient) -> None:
    details = _assert_validation_shape(probe_client.post("/probe", json={}))
    keys = [item["key"] for item in details]
    assert "firstName" in keys  # the missing field is named (contracts §2)


def test_422_tree_from_conftest_client_is_unified(client) -> None:
    """Even the live app (pre-migration schemas) must speak unified errors."""
    response = client.post("/api/v1/auth/login", json={"username": "x"})
    assert response.status_code == 422
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["errorCode"] == "validation_error"
