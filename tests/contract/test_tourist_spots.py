"""Contract: tourist spot management endpoints (feature 007 — contracts/tourist-spots.md).

Built up per user story (T005/T009 US1 CRUD+RBAC+audit; T010 catalog;
T012 schedule; T014 listing; T016 public detail). Admin-only management
operations answer 403 for anonymous/tourist/employee (SC-006); the
single-spot detail is public (RF27). Every failure path is the unified
``ApiError`` payload (FR-014).
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

SPOTS_URL = "/api/v1/tourist-spots"
EMPLOYEE_PASSWORD = "synthetic-employee-password-1"

ADMIN_LOGIN = "/api/v1/auth/login"
EMPLOYEE_LOGIN = "/api/v1/auth/login"
TOURIST_LOGIN = "/api/v1/tourists/login"

SPOT_VIEW_KEYS = {
    "id",
    "name",
    "description",
    "latitude",
    "longitude",
    "toleranceRadiusM",
    "status",
    "categories",
    "schedule",
    "createdAt",
    "updatedAt",
}

PUBLIC_SPOT_KEYS = {
    "id",
    "name",
    "description",
    "latitude",
    "longitude",
    "toleranceRadiusM",
    "status",
    "categories",
    "schedule",
    "events",
    "mapLink",
}

VALID_CREATE = {
    "name": "Mirante Pedra do Bauzinho",
    "description": "Mirante com vista para o vale e trilha curta.",
    "latitude": -22.7271,
    "longitude": -45.0366,
    "categories": ["nature"],
    "schedule": [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN,
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    token = login.json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _employee_token(client: TestClient) -> str:
    login = client.post(
        EMPLOYEE_LOGIN,
        json={"username": "maria.panel", "password": EMPLOYEE_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return login.json()["accessToken"]


def _tourist_token(client: TestClient) -> str:
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Ana",
            "lastName": "Silva",
            "countryOfOrigin": "Brasil",
            "cpf": "123.456.789-09",
            "passportNumber": None,
            "phone": "+5511999999999",
            "email": "ana@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        TOURIST_LOGIN,
        json={"email": "ana@example.com", "password": "long-enough-password-1"},
    )
    assert login.status_code == 200, login.text
    return login.json()["accessToken"]


def _assert_api_error(response, code: str) -> None:
    body = response.json()
    assert set(body) == {"errorCode", "message", "details"}
    assert body["errorCode"] == code


# ---------------------------------------------------------------------------
# US1 (T005): CRUD + RBAC + audit — SC-001/SC-004/SC-006/SC-007
# ---------------------------------------------------------------------------


def test_create_spot_201_echoes_full_state(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    response = client.post(SPOTS_URL, json=VALID_CREATE, headers=_admin_headers(client))
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == SPOT_VIEW_KEYS
    assert body["name"] == VALID_CREATE["name"]
    assert body["description"] == VALID_CREATE["description"]
    assert body["latitude"] == VALID_CREATE["latitude"]
    assert body["longitude"] == VALID_CREATE["longitude"]
    assert body["status"] == "open"  # FR-008 default (US4-1 is expanded in T014)
    assert body["categories"] == ["nature"]
    assert body["schedule"] == [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}]


def test_create_spot_audit_record_identifies_actor(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=_admin_headers(client)).json()
    records = [record for record in audit_logs.records if "tourist_spot" in record.getMessage()]
    assert len(records) == 1  # SC-004: exactly one entry per write
    assert "tourist_spot.create" in records[0].getMessage()
    assert "admin.panel" in records[0].getMessage()  # actor identity
    assert f"tourist-spot:{created['id']}" in records[0].getMessage()


def test_write_actions_by_non_admins_are_refused_without_audit(
    client: TestClient, seeded_admin: int, seeded_employee: int, audit_logs
) -> None:
    """Employee AND tourist sessions (valid tokens, wrong role) are 403;
    anonymous (no credentials) is 401 — both refused with zero audit."""
    employee_headers = {"Authorization": f"Bearer {_employee_token(client)}"}

    for method, url, payload in (
        ("POST", SPOTS_URL, VALID_CREATE),
        ("PATCH", f"{SPOTS_URL}/1", {"name": "X"}),
        ("DELETE", f"{SPOTS_URL}/1", None),
        ("GET", SPOTS_URL, None),
    ):
        call = getattr(client, method.lower())
        response = (
            call(url, json=payload, headers=employee_headers)
            if payload
            else call(url, headers=employee_headers)
        )
        assert response.status_code == 403, (method, url, response.status_code)
        _assert_api_error(response, "authorization_failed")

    # Tourist token: refused as well (SC-006 covers tourists).
    tourist_headers = {"Authorization": f"Bearer {_tourist_token(client)}"}
    for method, url, payload in (
        ("POST", SPOTS_URL, VALID_CREATE),
        ("PATCH", f"{SPOTS_URL}/1", {"name": "X"}),
        ("DELETE", f"{SPOTS_URL}/1", None),
        ("GET", SPOTS_URL, None),
    ):
        call = getattr(client, method.lower())
        response = (
            call(url, json=payload, headers=tourist_headers)
            if payload
            else call(url, headers=tourist_headers)
        )  # noqa: E501
        assert response.status_code == 403
        _assert_api_error(response, "authorization_failed")

    # SC-004: refused actions produce ZERO audit entries (fresh caplog per test).
    writes = [record for record in audit_logs.records if "tourist_spot." in record.getMessage()]
    assert writes == []


def test_spot_operations_without_token_are_401(client: TestClient) -> None:
    assert client.post(SPOTS_URL, json=VALID_CREATE).status_code == 401
    assert client.get(SPOTS_URL).status_code == 401
    assert client.patch(f"{SPOTS_URL}/1", json={"name": "X"}).status_code == 401
    assert client.delete(f"{SPOTS_URL}/1").status_code == 401


def test_partial_edit_reflects_only_submitted_fields(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    """FR-017: submit only name — the rest stays exactly as created."""
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=_admin_headers(client)).json()

    response = client.patch(
        f"{SPOTS_URL}/{created['id']}",
        json={"name": "Mirante Renomeado"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Mirante Renomeado"
    assert body["description"] == created["description"]
    assert body["latitude"] == created["latitude"]
    assert body["longitude"] == created["longitude"]
    assert body["status"] == created["status"]
    assert body["categories"] == created["categories"]
    assert body["schedule"] == created["schedule"]

    records = [record for record in audit_logs.records if "tourist_spot." in record.getMessage()]
    assert len(records) == 2  # create audit + edit audit (exactly one per write)


def test_edit_and_remove_unknown_spot_is_404(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    response = client.patch(f"{SPOTS_URL}/9999", json={"name": "X"}, headers=headers)
    assert response.status_code == 404
    _assert_api_error(response, "resource_not_found")
    response = client.delete(f"{SPOTS_URL}/9999", headers=headers)
    assert response.status_code == 404
    _assert_api_error(response, "resource_not_found")


def test_remove_then_spot_vanishes_from_listing(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    headers = _admin_headers(client)
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=headers).json()

    response = client.delete(f"{SPOTS_URL}/{created['id']}", headers=headers)
    assert response.status_code == 204
    assert response.content == b""

    listing = client.get(SPOTS_URL, headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0

    # Further edit/remove report 404 (unknown target — FR-004).
    assert (
        client.patch(
            f"{SPOTS_URL}/{created['id']}", json={"name": "X"}, headers=headers
        ).status_code
        == 404
    )
    assert client.delete(f"{SPOTS_URL}/{created['id']}", headers=headers).status_code == 404

    deletes = [
        record for record in audit_logs.records if "tourist_spot.delete" in record.getMessage()
    ]
    assert len(deletes) == 1


def test_create_spot_rejects_snake_case_and_unknown_keys(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    snake = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "name": "X", "opening_status": "open"},
        headers=headers,
    )
    assert snake.status_code == 422
    keys = [item["key"] for item in snake.json()["details"]]
    assert "opening_status" in keys
    unknown = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "name": "X", "nickname": "spot"},
        headers=headers,
    )
    assert unknown.status_code == 422
    keys = [item["key"] for item in unknown.json()["details"]]
    assert "nickname" in keys


def test_coordinate_validation_rejects_out_of_range(client: TestClient, seeded_admin: int) -> None:
    """SC-002: 100% of out-of-range WGS-84 writes rejected before storage."""
    headers = _admin_headers(client)
    for field in ("latitude", "longitude"):
        invalid = (91.0, -91.0, 100.0) if field == "latitude" else (181.0, -181.0, 1000.0)
        for value in invalid:
            payload = {**VALID_CREATE, field: value}
            response = client.post(SPOTS_URL, json=payload, headers=headers)
            assert response.status_code == 422, (field, value)
            _assert_api_error(response, "validation_error")
            details = response.json()["details"]
            assert any(item["key"] == field for item in details)
    # Range boundaries themselves are valid (±90 latitude, ±180 longitude).
    for field, value in (
        ("latitude", 0.0),
        ("latitude", 90.0),
        ("latitude", -90.0),
        ("longitude", 0.0),
        ("longitude", 180.0),
        ("longitude", -180.0),
    ):
        ok = client.post(
            SPOTS_URL,
            json={**VALID_CREATE, "description": f"boundary {field} {value}", field: value},
            headers=headers,
        )
        assert ok.status_code == 201, (field, value)


def test_coordinate_validation_rejected_on_edit_leaves_spot_unchanged(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=headers).json()
    response = client.patch(
        f"{SPOTS_URL}/{created['id']}",
        json={"latitude": 91.0},
        headers=headers,
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")
    body = response.json()
    # Nothing was altered: a valid follow-up edit still sees the old state.
    detail_after = client.patch(
        f"{SPOTS_URL}/{created['id']}",
        json={"name": "Nome Novo"},
        headers=headers,
    ).json()
    assert detail_after["latitude"] == created["latitude"]
    assert body["errorCode"] == "validation_error"


def test_dms_style_coordinates_are_rejected(client: TestClient, seeded_admin: int) -> None:
    """Decimal degrees only — a degrees/minutes/seconds string is not a number."""
    response = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "latitude": "-22°43'37S"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


# ---------------------------------------------------------------------------
# US2 (T010): categories validated against the configured catalog
# ---------------------------------------------------------------------------


def test_create_with_unknown_category_key_is_422(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    response = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "categories": ["festival"]},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "request_error")
    assert "festival" in response.json()["message"]
    # Nothing was created or altered (US2-2).
    listing = client.get(SPOTS_URL, headers=_admin_headers(client))
    assert listing.json()["total"] == 0
    spot_writes = [
        record for record in audit_logs.records if "tourist_spot." in record.getMessage()
    ]
    assert spot_writes == []  # no audit for refused writes


def test_create_with_zero_categories_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "categories": []},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_duplicate_category_keys_in_one_submission_are_422(
    client: TestClient, seeded_admin: int
) -> None:
    response = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "categories": ["nature", "nature"]},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "request_error")


def test_associations_persist_and_read_back_identically(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "categories": ["nature", "leisure"]},
        headers=headers,
    ).json()
    # Read-back via a no-op edit (FR-017) and via the listing.
    echoed = client.patch(f"{SPOTS_URL}/{created['id']}", json={}, headers=headers)
    assert echoed.status_code == 200
    assert echoed.json()["categories"] == ["nature", "leisure"]
    listed = client.get(SPOTS_URL, headers=headers).json()["items"][0]
    assert listed["categories"] == ["nature", "leisure"]


def test_orphan_category_key_passes_through_admin_reads(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    """Q2/R3: a stored key no longer in the config catalog is returned
    verbatim on admin reads (no filtering, no startup repair)."""
    headers = _admin_headers(client)
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=headers).json()

    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        TouristSpotCategory,
    )

    with sessionfactory_for() as session:
        session.add(TouristSpotCategory(spot_id=created["id"], category_key="roman"))
        session.commit()

    listed = client.get(SPOTS_URL, headers=headers).json()["items"][0]
    assert listed["categories"] == ["nature", "roman"]


def test_catalog_extension_by_configuration_is_accepted(
    client: TestClient, seeded_admin: int, tmp_path, monkeypatch
) -> None:
    """US2-4: extend the catalog ONLY via configuration data — accepted
    with zero code change."""
    import json as _json
    from pathlib import Path as _Path

    location_file = tmp_path / "location-extended.json"
    location_file.write_text(
        _json.dumps(
            {
                "city": "Passa Quatro",
                "city_timezone": "America/Sao_Paulo",
                "languages": ["pt-BR"],
                "interest_categories": [
                    {"key": "festival", "label": "Festival"},
                    {"key": "nature", "label": "Natureza"},
                ],
            }
        ),
        encoding="utf-8",
    )

    import passanorte_back.core.config as config_module
    from passanorte_back.core.config import Settings

    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: Settings(location_data_path=_Path(location_file)),
    )
    response = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "categories": ["festival"]},
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    assert response.json()["categories"] == ["festival"]


# ---------------------------------------------------------------------------
# US3 (T012): operating schedule validation — SC-003
# ---------------------------------------------------------------------------


def test_schedule_with_unknown_weekday_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [{"weekday": "funday", "opensAt": "08:00", "closesAt": "12:00"}],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_schedule_opening_equal_to_closing_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [{"weekday": "friday", "opensAt": "12:00", "closesAt": "12:00"}],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_schedule_opening_after_closing_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [{"weekday": "friday", "opensAt": "18:00", "closesAt": "08:00"}],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_malformed_schedule_times_are_422(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    for bad_opens in ("8:30", "25:00", "08:70", "08:30:00"):
        response = client.post(
            SPOTS_URL,
            json={
                **VALID_CREATE,
                "schedule": [{"weekday": "friday", "opensAt": bad_opens, "closesAt": "12:00"}],
            },
            headers=headers,
        )
        assert response.status_code == 422, bad_opens
        _assert_api_error(response, "validation_error")


def test_empty_schedule_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "schedule": []},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_overlapping_same_day_intervals_are_422(client: TestClient, seeded_admin: int) -> None:
    """US3-5: overlapping same-day submission rejected; nothing persists."""
    headers = _admin_headers(client)
    response = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [
                {"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"},
                {"weekday": "friday", "opensAt": "11:00", "closesAt": "18:00"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422
    _assert_api_error(response, "request_error")
    assert client.get(SPOTS_URL, headers=headers).json()["total"] == 0


def test_touching_intervals_on_same_day_are_valid(client: TestClient, seeded_admin: int) -> None:
    """Back-to-back intervals (close == next open) are unambiguous — they
    describe continuous operation (only strict overlap is rejected)."""
    response = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [
                {"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"},
                {"weekday": "friday", "opensAt": "12:00", "closesAt": "18:00"},
            ],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 201
    assert response.json()["schedule"] == [
        {"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"},
        {"weekday": "friday", "opensAt": "12:00", "closesAt": "18:00"},
    ]


def test_disjoint_same_day_intervals_are_persisted(client: TestClient, seeded_admin: int) -> None:
    """US3-4: multiple non-overlapping intervals for one weekday persist."""
    headers = _admin_headers(client)
    response = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [
                {"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"},
                {"weekday": "friday", "opensAt": "14:00", "closesAt": "18:00"},
                {"weekday": "sunday", "opensAt": "09:00", "closesAt": "11:00"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    schedule = response.json()["schedule"]
    assert schedule == [
        {"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"},
        {"weekday": "friday", "opensAt": "14:00", "closesAt": "18:00"},
        {"weekday": "sunday", "opensAt": "09:00", "closesAt": "11:00"},
    ]


def test_rejected_schedule_edit_leaves_previous_schedule_intact(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL,
        json={
            **VALID_CREATE,
            "schedule": [{"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"}],
        },
        headers=headers,
    ).json()
    response = client.patch(
        f"{SPOTS_URL}/{created['id']}",
        json={
            "schedule": [
                {"weekday": "friday", "opensAt": "08:00", "closesAt": "12:00"},
                {"weekday": "friday", "opensAt": "13:00", "closesAt": "14:00"},
                {"weekday": "friday", "opensAt": "13:30", "closesAt": "18:00"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422
    echoed = client.patch(f"{SPOTS_URL}/{created['id']}", json={}, headers=headers)
    assert echoed.json()["schedule"] == created["schedule"]


# ---------------------------------------------------------------------------
# US4 (T014): status lifecycle with filtering and bounded listing
# ---------------------------------------------------------------------------


def test_spot_created_without_status_is_open(client: TestClient, seeded_admin: int) -> None:
    body = client.post(SPOTS_URL, json=VALID_CREATE, headers=_admin_headers(client)).json()
    assert body["status"] == "open"  # FR-008/US4-1


def test_listing_filters_by_status(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    client.post(SPOTS_URL, json={**VALID_CREATE, "name": "A"}, headers=headers)  # open
    client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "name": "B", "status": "temporarilyClosed"},
        headers=headers,
    )
    client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "name": "C", "status": "permanentlyClosed"},
        headers=headers,
    )

    filtered = client.get(f"{SPOTS_URL}?status=temporarilyClosed", headers=headers)
    assert filtered.status_code == 200
    assert [item["name"] for item in filtered.json()["items"]] == ["B"]

    unfiltered = client.get(SPOTS_URL, headers=headers).json()
    assert unfiltered["total"] == 3  # US4-3: every status returned
    assert {item["name"] for item in unfiltered["items"]} == {"A", "B", "C"}


def test_status_transition_via_edit_persists(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "status": "temporarilyClosed"},
        headers=headers,
    ).json()
    updated = client.patch(f"{SPOTS_URL}/{created['id']}", json={"status": "open"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["status"] == "open"
    after = client.patch(f"{SPOTS_URL}/{created['id']}", json={}, headers=headers)
    assert after.json()["status"] == "open"


def test_unknown_status_filter_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.get(f"{SPOTS_URL}?status=junk", headers=_admin_headers(client))
    assert response.status_code == 422
    _assert_api_error(response, "request_error")


def test_unknown_status_value_on_write_is_422(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        SPOTS_URL, json={**VALID_CREATE, "status": "junk"}, headers=_admin_headers(client)
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_pagination_bounds_and_defaults(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    for index in range(3):
        client.post(SPOTS_URL, json={**VALID_CREATE, "name": f"P{index}"}, headers=headers)

    listing = client.get(SPOTS_URL, headers=headers).json()
    assert listing["page"] == 1 and listing["pageSize"] == 20
    assert listing["total"] >= 3

    paged = client.get(f"{SPOTS_URL}?page=1&pageSize=2", headers=headers).json()
    assert len(paged["items"]) == 2

    assert client.get(f"{SPOTS_URL}?page=0", headers=headers).status_code == 422
    assert client.get(f"{SPOTS_URL}?pageSize=0", headers=headers).status_code == 422
    assert client.get(f"{SPOTS_URL}?pageSize=101", headers=headers).status_code == 422


def test_removed_spot_never_appears_in_any_listing(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "status": "temporarilyClosed"},
        headers=headers,
    ).json()
    client.delete(f"{SPOTS_URL}/{created['id']}", headers=headers)
    for query in ("", "?status=open", "?status=temporarilyClosed", "?page=1&pageSize=100"):
        listing = client.get(f"{SPOTS_URL}{query}", headers=headers)
        assert listing.json()["total"] == 0, query
        assert listing.json()["items"] == []


# ---------------------------------------------------------------------------
# US5 (T016): public detail endpoint for the Passaporte app
# ---------------------------------------------------------------------------


def test_public_detail_without_credentials_returns_full_contract(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=headers).json()

    response = client.get(f"{SPOTS_URL}/{created['id']}")  # NO auth header
    assert response.status_code == 200
    body = response.json()
    assert set(body) == PUBLIC_SPOT_KEYS
    assert body["id"] == created["id"]
    assert body["name"] == created["name"]
    assert body["description"] == created["description"]
    assert body["status"] == "open"
    assert body["categories"] == [{"key": "nature", "label": "Natureza"}]
    assert body["schedule"] == [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}]
    assert body["events"] == []  # empty collection, never an error (R8)
    assert body["mapLink"] == ("https://www.google.com/maps/search/?api=1&query=-22.7271,-45.0366")


def test_public_detail_resolves_portuguese_labels(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "categories": ["nature", "gastronomy", "leisure"]},
        headers=headers,
    ).json()
    body = client.get(f"{SPOTS_URL}/{created['id']}").json()
    assert body["categories"] == [
        {"key": "nature", "label": "Natureza"},
        {"key": "gastronomy", "label": "Gastronomia"},
        {"key": "leisure", "label": "Lazer"},
    ]


def test_closed_spot_is_publicly_visible_with_status(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL,
        json={**VALID_CREATE, "status": "permanentlyClosed"},
        headers=headers,
    ).json()
    body = client.get(f"{SPOTS_URL}/{created['id']}").json()
    assert body["status"] == "permanentlyClosed"


def test_public_detail_unknown_or_removed_is_404(client: TestClient, seeded_admin: int) -> None:
    response = client.get(f"{SPOTS_URL}/9999")
    assert response.status_code == 404
    _assert_api_error(response, "resource_not_found")

    headers = _admin_headers(client)
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=headers).json()
    client.delete(f"{SPOTS_URL}/{created['id']}", headers=headers)
    removed = client.get(f"{SPOTS_URL}/{created['id']}")
    assert removed.status_code == 404
    _assert_api_error(removed, "resource_not_found")


def test_public_detail_orphan_category_label_is_null(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    """U1/Q2: stored key outside the configured catalog → label null."""
    headers = _admin_headers(client)
    created = client.post(SPOTS_URL, json=VALID_CREATE, headers=headers).json()

    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        TouristSpotCategory,
    )

    with sessionfactory_for() as session:
        session.add(TouristSpotCategory(spot_id=created["id"], category_key="roman"))
        session.commit()

    body = client.get(f"{SPOTS_URL}/{created['id']}").json()
    assert created["categories"] == ["nature"]
    assert body["categories"] == [
        {"key": "nature", "label": "Natureza"},
        {"key": "roman", "label": None},
    ]


def test_all_module_endpoints_carry_exactly_the_registry_tag(
    client: TestClient, seeded_admin: int
) -> None:
    """FR-013/US5-4: every tourist-spots path carries the single
    central-registry tag "Tourist Spots" and no other."""
    openapi = client.get("/openapi.json").json()
    spot_paths = {
        path: methods for path, methods in openapi["paths"].items() if path.startswith(SPOTS_URL)
    }
    assert spot_paths, "tourist-spots routes must exist"
    for path, methods in spot_paths.items():
        for method, operation in methods.items():
            if method == "parameters":
                continue
            assert operation["tags"] == ["Tourist Spots"], (path, method)
    registered = {tag["name"] for tag in openapi["tags"]}
    assert "Tourist Spots" in registered
