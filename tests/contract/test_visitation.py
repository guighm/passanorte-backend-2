"""Contract: visitation endpoints (feature 011 — contracts/visitation.md).

All endpoints ride the pre-mounted module router (tag ``Visitation`` from
the central registry — feature 006) and are tourist-exclusive
(``require_tourist``). Every failure path is the unified ``ApiError``
payload (spec 005). Built per user story: T006 US1 (201 inside radius +
FR-013 422 cases); T014 US2 (409 outside radius, nothing persisted);
T021 US4 (history + visited-spots projections).
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

VISITATION_URL = "/api/v1/visitation"
SPOTS_URL = "/api/v1/tourist-spots"
TOURIST_LOGIN = "/api/v1/tourists/login"

SPOT_ANCHOR = (-22.7271, -45.0366)

MARK_VIEW_KEYS = {
    "id",
    "spotId",
    "visitedAt",
    "latitude",
    "longitude",
    "firstVisit",
    "routeOutcomes",
}
VISITATION_VIEW_KEYS = {"id", "spotId", "visitedAt", "latitude", "longitude"}
VISITED_SPOT_KEYS = {"spotId", "firstVisitAt", "visitCount"}

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
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


_TOURIST_COUNTER = [0]


def _valid_cpf(core: str) -> str:
    """Real CPF check digits — the tourists schema validates checksums."""
    digits = [int(char) for char in core]
    first = (
        sum(value * weight for value, weight in zip(digits, range(10, 1, -1), strict=False)) % 11
    )
    dv1 = 0 if first < 2 else 11 - first
    second = (
        sum(value * weight for value, weight in zip([*digits, dv1], range(11, 1, -1), strict=False))
        % 11
    )
    dv2 = 0 if second < 2 else 11 - second
    return f"{core}{dv1}{dv2}"


def _tourist_headers(client: TestClient) -> dict[str, str]:
    """Register a fresh unique tourist and authenticate (each test gets its
    own identity — no cross-test carry-over)."""
    _TOURIST_COUNTER[0] += 1
    suffix = _TOURIST_COUNTER[0]
    raw = _valid_cpf(f"123456{suffix:03d}")
    cpf = f"{raw[:3]}.{raw[3:6]}.{raw[6:]}"
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Ana",
            "lastName": "Silva",
            "countryOfOrigin": "Brasil",
            "cpf": cpf,
            "passportNumber": None,
            "phone": f"+5511999{suffix:06d}",
            "email": f"visiting-tourist-{suffix}@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        TOURIST_LOGIN,
        json={
            "email": f"visiting-tourist-{suffix}@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _create_spot(client: TestClient, tolerance_radius_m: float | None = None) -> dict[str, object]:
    payload = {**VALID_CREATE}
    if tolerance_radius_m is not None:
        payload["toleranceRadiusM"] = tolerance_radius_m
    headers = _admin_headers(client)
    response = client.post(SPOTS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# US1 (T006): marking inside the radius — 201 + camelCase contract
# ---------------------------------------------------------------------------


def test_mark_inside_global_radius_returns_201_full_contract(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)  # no override ⇒ global default (100 m)
    headers = _tourist_headers(client)

    response = client.post(
        f"{VISITATION_URL}/spots/{spot['id']}/visits",
        json={"latitude": -22.7266, "longitude": -45.0366},  # ~55 m from the spot
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == MARK_VIEW_KEYS
    assert body["spotId"] == spot["id"]
    assert body["firstVisit"] is True
    assert body["routeOutcomes"] == []  # US3 is wired in its own increment
    assert body["latitude"] == -22.7266
    assert body["longitude"] == -45.0366
    assert body["visitedAt"]  # server-side timestamp present (research R8)


def test_mark_uses_per_spot_larger_radius_override(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client, tolerance_radius_m=200.0)
    headers = _tourist_headers(client)

    response = client.post(
        f"{VISITATION_URL}/spots/{spot['id']}/visits",
        json={"latitude": -22.7254, "longitude": -45.0366},  # ~190 m — beyond the 100 m default
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["firstVisit"] is True


# ---------------------------------------------------------------------------
# FR-013 (analyze C2): invalid coordinates are 422 before any distance math
# ---------------------------------------------------------------------------


def test_mark_rejects_out_of_wgs84_range_coordinates_422(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    headers = _tourist_headers(client)
    url = f"{VISITATION_URL}/spots/{spot['id']}/visits"

    for bad_payload in (
        {"latitude": 91.0, "longitude": -45.0366},
        {"latitude": -9.0, "longitude": 181.0},
    ):
        response = client.post(url, json=bad_payload, headers=headers)
        assert response.status_code == 422, response.text
        body = response.json()
        assert set(body) == {"errorCode", "message", "details"}  # unified ApiError


def test_mark_rejects_non_finite_and_snake_case_payload_422(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    headers = _tourist_headers(client)
    url = f"{VISITATION_URL}/spots/{spot['id']}/visits"

    inf_payload = '{"latitude": -22.7266, "longitude": -45.0366, "extra": 1}'
    response = client.post(url, content=inf_payload, headers={**headers})
    assert response.status_code == 422  # unknown key (strict border, spec 005)

    snake = '{"latitude": -22.7266, "longitude": -45.0366, "first_visit": true}'
    response = client.post(url, content=snake, headers={**headers})
    assert response.status_code == 422  # snake_case input is also rejected


# ---------------------------------------------------------------------------
# US2 (T014): outside the radius — 409 unified error, nothing persisted
# ---------------------------------------------------------------------------


def test_mark_outside_radius_returns_409_unified_error(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    headers = _tourist_headers(client)
    url = f"{VISITATION_URL}/spots/{spot['id']}/visits"

    response = client.post(
        url,
        json={"latitude": -22.6820, "longitude": -45.0366},  # ~5 km — SC-002 case
        headers=headers,
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert set(body) == {"errorCode", "message", "details"}
    # Unified platform taxonomy (spec 005 §2): 409 → "conflict"; the outside-
    # radius cause is carried by the message (no bespoke errorCode — core).
    assert body["errorCode"] == "conflict"
    assert "radius" in body["message"]

    # Nothing persisted: the history stays empty (spot id, any history view).
    history = client.get(f"{VISITATION_URL}/visitations", headers=headers).json()
    visited = client.get(f"{VISITATION_URL}/visited-spots", headers=headers).json()
    assert history == {"items": []}
    assert visited == {"items": []}


def test_mark_between_global_and_per_spot_radius_is_rejected(
    client: TestClient, seeded_admin: int
) -> None:
    # Global default (100 m) would accept ~80 m; the 25 m override rejects
    # (US2 scenario 2 — per-spot override is stricter).
    spot = _create_spot(client, tolerance_radius_m=25.0)
    headers = _tourist_headers(client)

    response = client.post(
        f"{VISITATION_URL}/spots/{spot['id']}/visits",
        json={"latitude": -22.7264, "longitude": -45.0366},  # ~78 m
        headers=headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["errorCode"] == "conflict"  # unified taxonomy (spec 005 §2)


# ---------------------------------------------------------------------------
# US4 (T021): history + visited-spots projections
# ---------------------------------------------------------------------------


def test_history_and_visited_spots_show_full_ledger(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    headers = _tourist_headers(client)
    url = f"{VISITATION_URL}/spots/{spot['id']}/visits"

    first = client.post(url, json={"latitude": -22.7266, "longitude": -45.0366}, headers=headers)
    second = client.post(url, json={"latitude": -22.7267, "longitude": -45.0366}, headers=headers)
    assert first.status_code == 201 and second.status_code == 201, first.text + second.text

    history = client.get(f"{VISITATION_URL}/visitations", headers=headers)
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 2
    for item in items:
        assert set(item) == VISITATION_VIEW_KEYS
        assert item["spotId"] == spot["id"]
    assert items[0]["latitude"] == -22.7267  # newest first
    assert items[1]["latitude"] == -22.7266

    visited = client.get(f"{VISITATION_URL}/visited-spots", headers=headers)
    assert visited.status_code == 200
    items = visited.json()["items"]
    assert len(items) == 1
    assert set(items[0]) == VISITED_SPOT_KEYS
    assert items[0]["spotId"] == spot["id"]
    assert items[0]["visitCount"] == 2
    assert items[0]["firstVisitAt"]  # MIN(visited_at) present


def test_empty_history_and_visited_spots_return_200_empty(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _tourist_headers(client)
    assert client.get(f"{VISITATION_URL}/visitations", headers=headers).json() == {"items": []}
    assert client.get(f"{VISITATION_URL}/visited-spots", headers=headers).json() == {"items": []}


def test_history_is_tourist_exclusive(client: TestClient, seeded_admin: int) -> None:
    # 401 anonymous; 403 for the admin (non-tourist RBAC — require_tourist).
    assert client.get(f"{VISITATION_URL}/visitations").status_code == 401
    admin = client.get(f"{VISITATION_URL}/visitations", headers=_admin_headers(client))
    assert admin.status_code == 403
    mark = client.post(f"{VISITATION_URL}/spots/1/visits", json={"latitude": 0.0, "longitude": 0.0})
    assert mark.status_code == 401


# ---------------------------------------------------------------------------
# Phase 8 Convergence (T025): missing edge-case coverage (404 / non-finite)
# ---------------------------------------------------------------------------


def test_mark_on_nonexistent_spot_returns_404(client: TestClient, seeded_admin: int) -> None:
    headers = _tourist_headers(client)
    response = client.post(
        f"{VISITATION_URL}/spots/999999/visits",
        json={"latitude": -22.7266, "longitude": -45.0366},
        headers=headers,
    )
    assert response.status_code == 404, response.text
    body = response.json()
    assert set(body) == {"errorCode", "message", "details"}
    assert body["errorCode"] == "resource_not_found"


def test_mark_on_removed_spot_returns_404(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    removed = client.delete(f"{SPOTS_URL}/{spot['id']}", headers=_admin_headers(client))
    assert removed.status_code == 204, removed.text

    headers = _tourist_headers(client)
    response = client.post(
        f"{VISITATION_URL}/spots/{spot['id']}/visits",
        json={"latitude": -22.7266, "longitude": -45.0366},  # the removed spot
        headers=headers,
    )
    assert response.status_code == 404, response.text
    assert response.json()["errorCode"] == "resource_not_found"


def test_mark_rejects_nan_and_infinity_coordinates_422(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    headers = _tourist_headers(client)
    url = f"{VISITATION_URL}/spots/{spot['id']}/visits"

    for raw_body in (
        '{"latitude": NaN, "longitude": -45.0366}',
        '{"latitude": -22.7266, "longitude": Infinity}',
    ):
        response = client.post(
            url,
            content=raw_body,
            headers={**headers, "content-type": "application/json"},
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["errorCode"] == "validation_error"  # unified taxonomy (spec 005 §2)

    history = client.get(f"{VISITATION_URL}/visitations", headers=headers).json()
    assert history == {"items": []}  # 422 before any distance math


# ---------------------------------------------------------------------------
# Phase 8 Convergence (T026): SC-003 immutability guard — no mutative path
# ---------------------------------------------------------------------------


def test_ledger_exposes_no_mutative_path(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    headers = _tourist_headers(client)
    marked = client.post(
        f"{VISITATION_URL}/spots/{spot['id']}/visits",
        json={"latitude": -22.7266, "longitude": -45.0366},
        headers=headers,
    )
    assert marked.status_code == 201, marked.text
    record_id = marked.json()["id"]

    # FR-006: records cannot be updated or deleted by any user operation —
    # existing paths answer 405 (method not allowed); unknown subpaths answer
    # 404. Every outcome leaves the ledger untouched (SC-003).
    for method, url in (
        ("patch", f"{VISITATION_URL}/visitations"),
        ("put", f"{VISITATION_URL}/visitations"),
        ("delete", f"{VISITATION_URL}/visitations"),
        ("patch", f"{VISITATION_URL}/visited-spots"),
        ("put", f"{VISITATION_URL}/spots/{spot['id']}/visits"),
        ("delete", f"{VISITATION_URL}/spots/{spot['id']}/visits"),
        ("patch", f"{VISITATION_URL}/visitations/{record_id}"),
        ("delete", f"{VISITATION_URL}/visitations/{record_id}"),
    ):
        response = client.request(method.upper(), url, json={"latitude": 0.0}, headers=headers)
        assert response.status_code in (404, 405), (method, url, response.text)

    # And the ledger still holds exactly the original immutable row.
    history = client.get(f"{VISITATION_URL}/visitations", headers=headers).json()
    assert len(history["items"]) == 1
    assert history["items"][0]["latitude"] == -22.7266
    assert history["items"][0]["id"] == record_id
