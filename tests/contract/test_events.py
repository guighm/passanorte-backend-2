"""Contract: events management endpoints (feature 008 — contracts/events.md).

Built up per user story (T005 US1 CRUD + RBAC + audit; T010 US2 listings +
public embedding). Management operations are admin-only; failures answer
the unified ``ApiError`` payload (404/409/403/401/422). The permanently
closed rule answers 409 ``conflict`` (research R2); anonymous callers are
401 ``authentication_failed`` (auth precedent, feature 002 — same as the
tourist-spots module).
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

EVENTS_URL = "/api/v1/events"
SPOTS_URL = "/api/v1/tourist-spots"
EMPLOYEE_PASSWORD = "synthetic-employee-password-1"

ADMIN_LOGIN = "/api/v1/auth/login"
TOURIST_LOGIN = "/api/v1/tourists/login"

EVENT_VIEW_KEYS = {"id", "spotId", "occurrenceDate", "description", "ticketPrice"}
EVENT_LIST_KEYS = {"items"}

VALID_SPOT = {
    "name": "Mirante Pedra do Bauzinho",
    "description": "Mirante com vista para o vale e trilha curta.",
    "latitude": -22.7271,
    "longitude": -45.0366,
    "categories": ["nature"],
    "schedule": [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
}

VALID_EVENT = {
    "occurrenceDate": "2026-12-08",
    "description": "Festival de luzes no mirante com apresentação local.",
    "ticketPrice": 15.50,
}

EMPLOYEE_PASSWORD_NOTE = "same synthetic password as tests/conftest.py"


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN,
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    token = login.json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _employee_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN,
        json={"username": "maria.panel", "password": EMPLOYEE_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _tourist_headers(client: TestClient) -> dict[str, str]:
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
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _assert_api_error(response, code: str) -> None:  # noqa: ANN001
    body = response.json()
    assert set(body) == {"errorCode", "message", "details"}
    assert body["errorCode"] == code


def _create_spot(client: TestClient, **overrides) -> dict:  # noqa: ANN003
    response = client.post(
        SPOTS_URL, json={**VALID_SPOT, **overrides}, headers=_admin_headers(client)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_event(client: TestClient, spot_id: int, **overrides) -> dict:  # noqa: ANN003
    response = client.post(
        EVENTS_URL,
        json={"spotId": spot_id, **VALID_EVENT, **overrides},
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# US1 (T005): CRUD + RBAC + audit — SC-001/SC-002/SC-004/SC-006
# ---------------------------------------------------------------------------


def test_create_event_201_echoes_full_camelcase_state(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    response = client.post(
        EVENTS_URL, json={"spotId": spot["id"], **VALID_EVENT}, headers=_admin_headers(client)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == EVENT_VIEW_KEYS
    assert body["spotId"] == spot["id"]
    assert body["occurrenceDate"] == "2026-12-08"
    assert body["description"] == VALID_EVENT["description"]
    assert body["ticketPrice"] == 15.50


def test_create_event_audit_record_identifies_actor(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    spot = _create_spot(client)
    created = _create_event(client, spot["id"])
    records = [
        record for record in audit_logs.records if '"action": "event.' in record.getMessage()
    ]
    assert len(records) == 1  # SC-004: exactly one entry per write
    message = records[0].getMessage()
    assert '"action": "event.create"' in message
    assert "admin.panel" in message  # actor identity
    assert f'"target": "event:{created["id"]}"' in message


def test_edit_event_200_and_audit(client: TestClient, seeded_admin: int, audit_logs) -> None:
    spot = _create_spot(client)
    created = _create_event(client, spot["id"])
    response = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"description": "Festival remarcado com entrada franca.", "ticketPrice": 0},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description"] == "Festival remarcado com entrada franca."
    assert body["ticketPrice"] == 0  # zero stays a free event on every read
    assert body["occurrenceDate"] == created["occurrenceDate"]  # omitted stays
    messages = [record.getMessage() for record in audit_logs.records]
    updates = [message for message in messages if '"action": "event.update"' in message]
    assert len(updates) == 1
    assert f'"target": "event:{created["id"]}"' in updates[0]


def test_edit_event_changing_spot_revalidates_new_target(
    client: TestClient, seeded_admin: int
) -> None:
    first = _create_spot(client)
    second = _create_spot(client, name="Casa de Cultura")
    created = _create_event(client, first["id"])
    response = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"spotId": second["id"]},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["spotId"] == second["id"]


def test_empty_patch_is_noop_without_audit(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    spot = _create_spot(client)
    created = _create_event(client, spot["id"])
    response = client.patch(
        f"{EVENTS_URL}/{created['id']}", json={}, headers=_admin_headers(client)
    )
    assert response.status_code == 200, response.text
    assert response.json() == created
    event_actions = [
        record for record in audit_logs.records if '"action": "event.' in record.getMessage()
    ]
    assert len(event_actions) == 1  # only the original create


def test_delete_event_204_and_audit(client: TestClient, seeded_admin: int, audit_logs) -> None:
    spot = _create_spot(client)
    created = _create_event(client, spot["id"])
    response = client.delete(f"{EVENTS_URL}/{created['id']}", headers=_admin_headers(client))
    assert response.status_code == 204, response.text
    listing = client.get(EVENTS_URL, headers=_admin_headers(client))
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    messages = [record.getMessage() for record in audit_logs.records]
    assert any('"action": "event.delete"' in message for message in messages)


def test_event_write_refused_for_unknown_spot_404(client: TestClient, seeded_admin: int) -> None:
    response = client.post(
        EVENTS_URL, json={"spotId": 424242, **VALID_EVENT}, headers=_admin_headers(client)
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


def test_edit_refused_for_unknown_target_spot_keeps_state(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    created = _create_event(client, spot["id"])
    response = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"spotId": 424242},
        headers=_admin_headers(client),
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")
    kept = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"description": "still here"},
        headers=_admin_headers(client),
    )
    assert kept.status_code == 200
    assert kept.json()["spotId"] == spot["id"]


def test_edit_refused_for_unknown_event_404(client: TestClient, seeded_admin: int) -> None:
    response = client.patch(
        f"{EVENTS_URL}/99999", json={"description": "x"}, headers=_admin_headers(client)
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")
    delete_response = client.delete(f"{EVENTS_URL}/99999", headers=_admin_headers(client))
    assert delete_response.status_code == 404
    _assert_api_error(delete_response, "resource_not_found")


def test_create_refused_for_permanently_closed_spot_409(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    closed = client.patch(
        f"{SPOTS_URL}/{spot['id']}",
        json={"status": "permanentlyClosed"},
        headers=_admin_headers(client),
    )
    assert closed.status_code == 200, closed.text
    response = client.post(
        EVENTS_URL, json={"spotId": spot["id"], **VALID_EVENT}, headers=_admin_headers(client)
    )
    assert response.status_code == 409, response.text
    _assert_api_error(response, "conflict")
    assert "permanently closed" in response.json()["message"].lower()


def test_edit_to_permanently_closed_spot_refused_409_keeps_state(
    client: TestClient, seeded_admin: int
) -> None:
    first = _create_spot(client)
    second = _create_spot(client, name="Casa de Cultura")
    created = _create_event(client, first["id"])
    client.patch(
        f"{SPOTS_URL}/{second['id']}",
        json={"status": "permanentlyClosed"},
        headers=_admin_headers(client),
    )
    response = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"spotId": second["id"]},
        headers=_admin_headers(client),
    )
    assert response.status_code == 409, response.text
    _assert_api_error(response, "conflict")
    kept = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"description": "unchanged otherwise"},
        headers=_admin_headers(client),
    )
    assert kept.status_code == 200
    assert kept.json()["spotId"] == first["id"]


def test_event_writes_refused_for_non_admins_without_audit(
    client: TestClient, seeded_admin: int, seeded_employee: int, audit_logs
) -> None:
    """Employee AND tourist sessions (valid tokens, wrong role) are 403;
    anonymous (no credentials) is 401 — both refused with zero audit."""
    spot = _create_spot(client)
    for headers, expected_status in (
        (_employee_headers(client), 403),
        (_tourist_headers(client), 403),
        ({}, 401),
    ):
        for method, url, payload in (
            ("POST", EVENTS_URL, {"spotId": spot["id"], **VALID_EVENT}),
            ("PATCH", f"{EVENTS_URL}/{spot['id']}", {"description": "x"}),
            ("DELETE", f"{EVENTS_URL}/1", None),
        ):
            call = getattr(client, method.lower())
            kwargs: dict = {"headers": headers}
            if payload is not None:
                kwargs["json"] = payload
            response = call(url, **kwargs)
            assert response.status_code == expected_status, (method, response.text)
            if expected_status == 403:
                _assert_api_error(response, "authorization_failed")
            else:
                _assert_api_error(response, "authentication_failed")
    event_actions = [
        record for record in audit_logs.records if '"action": "event.' in record.getMessage()
    ]
    assert event_actions == []


def test_create_shape_violations_422(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    headers = _admin_headers(client)
    shape_cases = (
        {"spotId": spot["id"], **VALID_EVENT, "surprise": 1},  # unknown key
        {  # snake_case key rejected at the border
            "spot_id": spot["id"],
            "occurrenceDate": "2026-12-08",
            "description": "x",
            "ticketPrice": 0,
        },
        {"spotId": spot["id"], **VALID_EVENT, "ticketPrice": -0.01},  # negative
        {"spotId": spot["id"], **VALID_EVENT, "ticketPrice": 15.505},  # >2dp
        {"spotId": spot["id"], **VALID_EVENT, "occurrenceDate": "08-12-2026"},
        {"spotId": spot["id"], **VALID_EVENT, "occurrenceDate": "2026-12"},
        {"spotId": spot["id"], **VALID_EVENT, "description": ""},
        {"spotId": spot["id"], **VALID_EVENT, "description": "x" * 2001},
        {key: value for key, value in VALID_EVENT.items()},  # missing spotId
    )
    for payload in shape_cases:
        response = client.post(EVENTS_URL, json=payload, headers=headers)
        assert response.status_code == 422, (payload, response.text)
        _assert_api_error(response, "validation_error")


def test_edit_shape_violations_422(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    created = _create_event(client, spot["id"])
    headers = _admin_headers(client)
    for payload in (
        {"ticketPrice": -1},
        {"ticketPrice": 0.001},
        {"occurrenceDate": "yesterday"},
    ):
        response = client.patch(f"{EVENTS_URL}/{created['id']}", json=payload, headers=headers)
        assert response.status_code == 422, (payload, response.text)
        _assert_api_error(response, "validation_error")


# ---------------------------------------------------------------------------
# US2 (T010): filtered listing + public embedding — SC-003/SC-006
# ---------------------------------------------------------------------------


def _seed_spot_with_events(client: TestClient, count: int = 3) -> tuple[dict, list[dict]]:
    spot = _create_spot(client)
    dates = ["2026-12-05", "2026-12-08", "2026-12-20"]
    created = [
        _create_event(client, spot["id"], occurrenceDate=date_value, ticketPrice=float(index))
        for index, date_value in zip(range(count), dates[:count], strict=True)
    ]
    return spot, created


def test_listing_by_spot_returns_only_that_spots_events_in_order(
    client: TestClient, seeded_admin: int
) -> None:
    first, created = _seed_spot_with_events(client)
    _create_spot(client, name="Casa de Cultura")  # another spot: must stay out
    response = client.get(
        EVENTS_URL, params={"spotId": first["id"]}, headers=_admin_headers(client)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == EVENT_LIST_KEYS
    returned = body["items"]
    assert [item["id"] for item in returned] == [item["id"] for item in created]
    assert all(item["spotId"] == first["id"] for item in returned)
    # stable (occurrenceDate, id) order
    assert returned == sorted(returned, key=lambda item: (item["occurrenceDate"], item["id"]))


def test_listing_by_date_range_is_inclusive(client: TestClient, seeded_admin: int) -> None:
    _spot, created = _seed_spot_with_events(client)  # dates 05/08/20
    headers = _admin_headers(client)
    inside_lows = client.get(
        EVENTS_URL,
        params={"startDate": "2026-12-05", "endDate": "2026-12-08"},
        headers=headers,
    )
    assert inside_lows.status_code == 200
    assert [item["id"] for item in inside_lows.json()["items"]] == [
        created[0]["id"],
        created[1]["id"],
    ]
    # single-bound ranges include the bound events (inclusive semantics)
    only_start = client.get(EVENTS_URL, params={"startDate": "2026-12-20"}, headers=headers)
    assert [item["id"] for item in only_start.json()["items"]] == [created[2]["id"]]
    only_end = client.get(EVENTS_URL, params={"endDate": "2026-12-05"}, headers=headers)
    assert [item["id"] for item in only_end.json()["items"]] == [created[0]["id"]]


def test_listing_combined_filter_spot_and_range(client: TestClient, seeded_admin: int) -> None:
    spot, created = _seed_spot_with_events(client)
    other = _create_spot(client, name="Casa de Cultura")
    _create_event(client, other["id"], occurrenceDate="2026-12-08")
    response = client.get(
        EVENTS_URL,
        params={"spotId": spot["id"], "startDate": "2026-12-05", "endDate": "2026-12-08"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        created[0]["id"],
        created[1]["id"],
    ]


def test_listing_without_filters_or_matches_returns_all_or_empty(
    client: TestClient, seeded_admin: int
) -> None:
    _spot, created = _seed_spot_with_events(client)
    everything = client.get(EVENTS_URL, headers=_admin_headers(client))
    assert everything.status_code == 200
    assert {item["id"] for item in everything.json()["items"]} == {item["id"] for item in created}
    empty = client.get(
        EVENTS_URL,
        params={"startDate": "2030-01-01", "endDate": "2030-01-31"},
        headers=_admin_headers(client),
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_listing_refused_for_unknown_spot_filter_404(client: TestClient, seeded_admin: int) -> None:
    response = client.get(EVENTS_URL, params={"spotId": 424242}, headers=_admin_headers(client))
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


def test_listing_inverted_range_422_request_error(client: TestClient, seeded_admin: int) -> None:
    response = client.get(
        EVENTS_URL,
        params={"startDate": "2026-12-08", "endDate": "2026-12-05"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422, response.text
    _assert_api_error(response, "request_error")


def test_listing_malformed_query_422_validation_error(
    client: TestClient, seeded_admin: int
) -> None:
    response = client.get(
        EVENTS_URL, params={"startDate": "yesterday"}, headers=_admin_headers(client)
    )
    assert response.status_code == 422
    _assert_api_error(response, "validation_error")


def test_listing_refused_for_non_admins(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    for headers, expected_status, expected_code in (
        (_employee_headers(client), 403, "authorization_failed"),
        (_tourist_headers(client), 403, "authorization_failed"),
        ({}, 401, "authentication_failed"),
    ):
        response = client.get(EVENTS_URL, headers=headers)
        assert response.status_code == expected_status, response.text
        _assert_api_error(response, expected_code)


def test_public_spot_detail_embeds_events(client: TestClient, seeded_admin: int) -> None:
    spot, created = _seed_spot_with_events(client)
    response = client.get(f"{SPOTS_URL}/{spot['id']}")  # anonymous (RF27)
    assert response.status_code == 200, response.text
    embedded = response.json()["events"]
    assert [item["id"] for item in embedded] == [item["id"] for item in created]
    assert set(embedded[0]) == EVENT_VIEW_KEYS
    assert embedded[0]["occurrenceDate"] == "2026-12-05"
    assert embedded[0]["spotId"] == spot["id"]
    assert embedded[0]["ticketPrice"] == 0.0


def test_public_spot_detail_renders_empty_events_without_any(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    response = client.get(f"{SPOTS_URL}/{spot['id']}")
    assert response.status_code == 200
    assert response.json()["events"] == []


def test_public_detail_of_permanently_closed_spot_keeps_events(
    client: TestClient, seeded_admin: int
) -> None:
    spot, created = _seed_spot_with_events(client, count=1)
    client.patch(
        f"{SPOTS_URL}/{spot['id']}",
        json={"status": "permanentlyClosed"},
        headers=_admin_headers(client),
    )
    response = client.get(f"{SPOTS_URL}/{spot['id']}")  # anonymous
    assert response.status_code == 200  # spec 007: closed spots stay visible
    embedded = response.json()["events"]
    assert [item["id"] for item in embedded] == [created[0]["id"]]
