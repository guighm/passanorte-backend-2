"""Contract: strict camelCase-only input (spec 005 FR-003/FR-004).

US2 matrix against the core contract infra via a probe app (endpoint-
independent — live-endpoint strictness is asserted by US3 task tests).
Snake_case and unknown keys → 422 naming the received key; the whole body
fails together (no partial application); nested trees obey the rule;
underscore *values* never violate.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from passanorte_back.core.error_handlers import register_error_handlers
from passanorte_back.core.schemas import ApiModel


class _Address(ApiModel):
    postal_code: str


class _Item(ApiModel):
    unit_price: float


class _NestedProbe(ApiModel):
    first_name: str
    address: _Address
    items: list[_Item]


class _FlatProbe(ApiModel):
    email: str
    note: str


def _build_probe_app() -> FastAPI:
    app_fastapi = FastAPI()
    register_error_handlers(app_fastapi)

    @app_fastapi.post("/nested")
    def nested(data: _NestedProbe) -> dict[str, Any]:
        return {"receivedFirstName": data.first_name, "itemsCount": len(data.items)}

    @app_fastapi.post("/flat")
    def flat(data: _FlatProbe) -> dict[str, Any]:
        return {"receivedEmail": data.email}

    return app_fastapi


@pytest.fixture
def probe_client() -> TestClient:
    return TestClient(_build_probe_app(), raise_server_exceptions=False)


def test_camel_tree_is_accepted(probe_client: TestClient) -> None:
    response = probe_client.post(
        "/nested",
        json={
            "firstName": "Ana",
            "address": {"postalCode": "12345-000"},
            "items": [{"unitPrice": 9.5}],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"receivedFirstName": "Ana", "itemsCount": 1}


def test_snake_case_field_is_accepted_camel_only(probe_client: TestClient) -> None:
    assert probe_client.post("/flat", json={"email": "a@b.c", "note": "ok"}).status_code == 200


def test_nested_snake_key_names_full_path_in_details(probe_client: TestClient) -> None:
    response = probe_client.post(
        "/nested",
        json={
            "firstName": "Ana",
            "address": {"postal_code": "12345-000"},
            "items": [{"unitPrice": 9.5}],
        },
    )
    assert response.status_code == 422
    keys = [item["key"] for item in response.json()["details"]]
    assert "address.postal_code" in keys


def test_list_items_snake_key_is_rejected(probe_client: TestClient) -> None:
    response = probe_client.post(
        "/nested",
        json={"firstName": "Ana", "address": {"postalCode": "1"}, "items": [{"unit_price": 9.5}]},
    )
    assert response.status_code == 422
    keys = [item["key"] for item in response.json()["details"]]
    assert "items.0.unit_price" in keys


def test_mixed_keys_fail_together_no_partial_application(probe_client: TestClient) -> None:
    response = probe_client.post("/flat", json={"email": "a@b.c", "fullName": "Ana"})
    assert response.status_code == 422
    keys = [item["key"] for item in response.json()["details"]]
    assert "fullName" in keys  # unknown camel key is still an unknown key


def test_underscore_values_never_violate(probe_client: TestClient) -> None:
    response = probe_client.post(
        "/flat", json={"email": "ana_silva@example.com", "note": "first_name_tourist"}
    )
    assert response.status_code == 200
    assert not response.json()["receivedEmail"].endswith(".invalid")
