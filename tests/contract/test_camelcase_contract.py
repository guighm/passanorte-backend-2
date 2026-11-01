"""Contract sweep: the camelCase JSON contract across ALL endpoints.

Spec 005 FR-011 / SC-001: this suite walks every registered route and the
generated OpenAPI document, failing whenever any JSON key at any nesting
level contains an underscore. Detector canaries prove the check is not
vacuous. Pending-migration surfaces (schemas still on plain ``BaseModel`` —
US3 tasks T012–T019) are excluded from the static alias assertion and the
exclusion list empties once modules migrate (T015/T019).

Sources (spec.md US1 — clarification of remediation C2):
- static: every response-model subtree attached to a route must be an
  ``ApiModel`` with snake_case-free aliases;
- static: the OpenAPI document registers ``ApiError`` (unified error DTO);
- runtime: every route receives a minimal unauthenticated request and every
  returned JSON body (success, 422/401/404/… or 204) is swept recursively.
"""

import re
import typing
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from passanorte_back.core.schemas import ApiModel
from passanorte_back.main import app
from tests.contract._camelcase import has_snake_case_keys

# ---------------------------------------------------------------- helpers


def _collect_model_subtree(annotation: Any, seen: set[type]) -> None:
    origin = typing.get_origin(annotation)
    for arg in typing.get_args(annotation) if origin else []:
        _collect_model_subtree(arg, seen)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return
        seen.add(annotation)
        for field in annotation.model_fields.values():
            _collect_model_subtree(field.annotation, seen)


def _route_models(route: APIRoute) -> set[type]:
    models: set[type] = set()
    if route.response_model is not None:
        _collect_model_subtree(route.response_model, models)
    return models


def _all_api_routes() -> list[APIRoute]:
    """Every APIRoute, flattening ``_IncludedRouter`` wrappers (FastAPI 0.162)."""
    routes: list[APIRoute] = []
    for entry in app.routes:
        if isinstance(entry, APIRoute):
            routes.append(entry)
        elif hasattr(entry, "original_router"):
            routes.extend(
                route for route in entry.original_router.routes if isinstance(route, APIRoute)
            )
    return routes


def _unmigrated_routes() -> list[str]:
    """Names of routes whose response-model subtree is not yet ``ApiModel``."""
    pending = []
    for route in _all_api_routes():
        models = _route_models(route)
        if models and not all(issubclass(model, ApiModel) for model in models):
            pending.append(f"{sorted(route.methods)} {route.path}")
    return pending


def _every_alias_snake_free(models: set[type]) -> None:
    for model in models:
        for field in model.model_fields.values():
            alias = field.alias or field.name
            assert "_" not in str(alias), (
                f"{model.__name__}.['{alias}'] still carries an underscore"
            )


# ------------------------------------------------------------------- T008


def test_detector_canary_planted_snake_key_is_red() -> None:
    """SC-001: the sweep detector is not vacuous."""
    planted: dict[str, Any] = {"accessToken": "x", "refresh_token": "planted"}
    assert has_snake_case_keys(planted) is True


def test_openapi_registers_unified_error_dto() -> None:
    """FR-005/Q1: the unified error schema is registered in Swagger."""
    schemas = app.openapi()["components"]["schemas"]
    assert "ApiError" in schemas
    assert "ApiErrorKeyDetails" in schemas


def test_migrated_response_models_have_snake_free_aliases() -> None:
    """FR-001 (static leg, exclusion-free — US3): every response-model tree."""
    for route in _all_api_routes():
        models = _route_models(route)
        assert all(issubclass(model, ApiModel) for model in models), (
            f"route {route.path} exposes non-ApiModel schemas"
        )
        _every_alias_snake_free(models)


def _minimal_request(client: TestClient, route: APIRoute) -> None:
    path = re.sub(r"\{[^}]+\}", "0", route.path)
    methods = sorted(route.methods - {"HEAD", "OPTIONS"})
    method = "POST" if "POST" in methods else ("PUT" if "PUT" in methods else methods[0])
    kwargs: dict[str, Any] = {"json": {}} if method in {"POST", "PUT", "PATCH"} else {}
    response = client.request(method, path, **kwargs)
    if response.status_code == 204 or not response.content:
        return
    body = response.json()
    assert not has_snake_case_keys(body), f"route {route.path} returned snake_case keys"


def test_runtime_sweep_every_route_body_is_snake_free(client: TestClient) -> None:
    """FR-011 (runtime leg): any JSON body returned by any route is swept."""
    for route in _all_api_routes():
        _minimal_request(client, route)
    # root-level health probe stays inside the sweep (research R6)
    response = client.get("/health")
    if response.status_code != 204 and response.content:
        assert not has_snake_case_keys(response.json())


def test_no_pending_migration_surfaces_remain() -> None:
    """US3 complete: zero routes still expose plain-BaseModel responses."""
    assert _unmigrated_routes() == []


# ------------------------------------------------------- US4 (tasks T020/T021)

_DTO_VIOLATION_FIXTURE = {
    # canned mini-OpenAPI (T020 RED procedure): deliberate violations —
    # lowercase DTO name + snake_case property — must be caught by the
    # same assertions applied to the real document below
    "lowercaseDto": {"properties": {"bad_key": {"type": "string"}}},
    "GoodDto": {"properties": {"goodKey": {"type": "string"}}},
}


def _assert_pascal_case_dto_names(schemas: dict) -> None:
    for name in schemas:
        assert name[0].isupper() and "_" not in name, f"DTO name violates PascalCase: {name}"


def _assert_properties_snake_free(schemas: dict) -> None:
    for name, schema in schemas.items():
        for prop in schema.get("properties", {}):
            assert "_" not in prop, f"{name}.{prop} contains an underscore"


def test_canned_fixture_proves_dto_rules_catch_violations() -> None:
    """T020 RED procedure (deterministic): the rules fail on violations."""
    with pytest.raises(AssertionError):
        _assert_pascal_case_dto_names(_DTO_VIOLATION_FIXTURE)
    with pytest.raises(AssertionError):
        _assert_properties_snake_free(_DTO_VIOLATION_FIXTURE)
    with pytest.raises(AssertionError):
        _assert_properties_snake_free({"GoodDto": {"properties": {"bad_key": {}}}})


def test_openapi_dto_names_and_properties_follow_contract() -> None:
    """FR-006/FR-007: real Swagger is the frontend TS source of truth."""
    schemas = app.openapi()["components"]["schemas"]
    _assert_pascal_case_dto_names(schemas)
    _assert_properties_snake_free(schemas)
    migrated = {
        "SessionResponse",
        "LoginRequest",
        "RefreshRequest",
        "CurrentUserResponse",
        "EmployeeCreateRequest",
        "EmployeeCreatedResponse",
        "EmployeeListResponse",
        "EmployeeUpdateRequest",
        "EmployeeView",
        "TouristCreateRequest",
        "TouristLoginRequest",
        "TouristRegistered",
        "TouristSessionResponse",
        "TouristProfileResponse",
        "TouristUpdateRequest",
        "InterestCategory",
        "InterestCategoriesResponse",
        "TouristInterestsResponse",
        "TouristInterestsUpdateRequest",
    }
    assert migrated.issubset(schemas)  # all shipped DTOs exposed to TS generation
