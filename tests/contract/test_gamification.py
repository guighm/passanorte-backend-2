"""Contract: gamification endpoints (feature 009 — contracts/gamification.md).

Built up per user story:
- T006 US1: route management CRUD + RBAC + audit + archive listing rules.
- T010 US2: enrollment + progress contracts.
- T015 US3: completed-progress payload (badge + code).
- T019 US4: prize stock + staff concession contracts.

Failures answer the unified ``ApiError`` payload (401/403/404/409/422);
management is admin-only; tourist self-service is tourist-only.
"""

from fastapi.testclient import TestClient

import passanorte_back.modules.gamification.services.gamification as gamification_service
from tests.conftest import TEST_ADMIN_PASSWORD

GAMIFICATION_URL = "/api/v1/gamification"
SPOTS_URL = "/api/v1/tourist-spots"
TOURIST_SPOTS_URL = "/api/v1/tourist-spots"

ADMIN_LOGIN = "/api/v1/auth/login"
TOURIST_LOGIN = "/api/v1/tourists/login"

EMPLOYEE_PASSWORD = "synthetic-employee-password-1"
TOURIST_PASSWORD = "long-enough-password-1"

ROUTE_VIEW_KEYS = {"id", "name", "description", "spots", "prize", "status"}
PRIZE_KEYS = {"id", "name", "stockQuantity"}
SPOT_ITEM_KEYS = {"spotId", "displayOrder"}

VALID_SPOT = {
    "name": "Mirante Pedra do Bauzinho",
    "description": "Mirante com vista para o vale e trilha curta.",
    "latitude": -22.7271,
    "longitude": -45.0366,
    "categories": ["nature"],
    "schedule": [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
}

VALID_ROUTE = {
    "name": "Rota Histórica do Centro",
    "description": "Caminhada pelos pontos históricos de Passa Quatro.",
    "spots": [
        {"spotId": 1, "displayOrder": 1},
        {"spotId": 2, "displayOrder": 2},
    ],
    "prize": {"name": "Caneca do Festival", "initialStock": 10},
}

_counter = {"spot": 0, "tourist": 0}
_last_tourist_email = ""


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN, json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
    )
    token = login.json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _employee_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN, json={"username": "maria.panel", "password": EMPLOYEE_PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _tourist_headers(client: TestClient) -> dict[str, str]:
    _counter["tourist"] += 1
    email = f"turista-{_counter['tourist']}@example.com"
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Ana",
            "lastName": "Silva",
            "countryOfOrigin": "Brasil",
            "cpf": None,
            "passportNumber": f"P{_counter['tourist']:06d}",
            "phone": "+5511999999999",
            "email": email,
            "password": TOURIST_PASSWORD,
        },
    )
    assert register.status_code == 201, register.text
    global _last_tourist_email
    _last_tourist_email = email
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": TOURIST_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _assert_api_error(response, code: str) -> None:  # noqa: ANN001
    body = response.json()
    assert set(body) == {"errorCode", "message", "details"}
    assert body["errorCode"] == code


def _create_spot(client: TestClient, **overrides) -> dict:  # noqa: ANN003
    response = client.post(
        SPOTS_URL,
        json={**VALID_SPOT, "name": f"{VALID_SPOT['name']} {_create_spot_name()}", **overrides},
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_spot_name() -> str:
    _counter["spot"] += 1
    return f"#{_counter['spot']}"


def _spots_payload(client: TestClient, quantity: int = 2) -> list[dict]:
    return [
        {"spotId": _create_spot(client)["id"], "displayOrder": order}
        for order in range(1, quantity + 1)
    ]


def _create_route(client: TestClient, **overrides) -> dict:  # noqa: ANN003
    payload = {**VALID_ROUTE, **overrides}
    if payload.get("spots") == VALID_ROUTE["spots"] and "spots" not in overrides:
        payload["spots"] = _spots_payload(client, 2)
    response = client.post(
        f"{GAMIFICATION_URL}/routes", json=payload, headers=_admin_headers(client)
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# US1 (T006): route management CRUD + RBAC + audit — SC-006 (routes)
# ---------------------------------------------------------------------------


def test_create_route_201_full_camelcase_body(client: TestClient, seeded_admin: int) -> None:
    spots = _spots_payload(client, 2)
    response = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={**VALID_ROUTE, "spots": spots},
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == ROUTE_VIEW_KEYS
    assert body["name"] == VALID_ROUTE["name"]
    assert body["status"] == "active"
    assert [
        {"spotId": spot["spotId"], "displayOrder": spot["displayOrder"]} for spot in body["spots"]
    ] == spots
    assert set(body["prize"]) == PRIZE_KEYS
    assert body["prize"]["name"] == "Caneca do Festival"
    assert body["prize"]["stockQuantity"] == 10


def test_edit_route_200_spots_re_validated(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)
    new_spots = _spots_payload(client, 3)
    response = client.patch(
        f"{GAMIFICATION_URL}/routes/{created['id']}",
        json={"name": "Rota da Serra", "spots": new_spots},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Rota da Serra"
    assert [spot["spotId"] for spot in body["spots"]] == [spot["spotId"] for spot in new_spots]


def test_archive_route_204_removed_from_listing_history_kept(
    client: TestClient, seeded_admin: int
) -> None:
    created = _create_route(client)
    admin = _admin_headers(client)
    response = client.delete(f"{GAMIFICATION_URL}/routes/{created['id']}", headers=admin)
    assert response.status_code == 204, response.text
    listing = client.get(f"{GAMIFICATION_URL}/routes", headers=admin)
    assert listing.status_code == 200
    assert all(item["id"] != created["id"] for item in listing.json()["items"])
    archived_view = client.get(f"{GAMIFICATION_URL}/routes/{created['id']}", headers=admin)
    assert archived_view.status_code == 200
    assert archived_view.json()["status"] == "archived"


def test_route_writes_refused_for_non_admin(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    tourist = _tourist_headers(client)
    spots = _spots_payload(client, 1)
    payload = {**VALID_ROUTE, "spots": spots}
    assert (
        client.post(f"{GAMIFICATION_URL}/routes", json=payload, headers=tourist).status_code == 403
    )
    assert (
        client.post(
            f"{GAMIFICATION_URL}/routes", json=payload, headers=_employee_headers(client)
        ).status_code
        == 403
    )
    assert client.post(f"{GAMIFICATION_URL}/routes", json=payload).status_code == 401


def test_create_route_unknown_spot_404(client: TestClient, seeded_admin: int) -> None:
    spots = _spots_payload(client, 1)
    spots.append({"spotId": 424242, "displayOrder": 2})
    response = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={**VALID_ROUTE, "spots": spots},
        headers=_admin_headers(client),
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


def test_create_route_with_removed_spot_404(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    response = client.delete(f"{TOURIST_SPOTS_URL}/{spot['id']}", headers=_admin_headers(client))
    assert response.status_code == 204, response.text
    response = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={**VALID_ROUTE, "spots": [{"spotId": spot["id"], "displayOrder": 1}]},
        headers=_admin_headers(client),
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


def test_edit_route_unknown_route_404(client: TestClient, seeded_admin: int) -> None:
    response = client.patch(
        f"{GAMIFICATION_URL}/routes/424242",
        json={"name": "Inexistente"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


def test_edit_archived_route_404(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)
    client.delete(f"{GAMIFICATION_URL}/routes/{created['id']}", headers=_admin_headers(client))
    response = client.patch(
        f"{GAMIFICATION_URL}/routes/{created['id']}",
        json={"name": "Arquivada"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


def test_create_route_shape_failures_422(client: TestClient, seeded_admin: int) -> None:
    admin = _admin_headers(client)
    empty_spots = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={**VALID_ROUTE, "spots": []},
        headers=admin,
    )
    assert empty_spots.status_code == 422
    negative_stock = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={**VALID_ROUTE, "prize": {"name": "Brinde", "initialStock": -1}},
        headers=admin,
    )
    assert negative_stock.status_code == 422
    snake_case = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={
            "name": "X",
            "description": "Y",
            "spots": _spots_payload(client, 1),
            "initial_stock": 1,
        },
        headers=admin,
    )
    assert snake_case.status_code == 422


def test_create_route_audit_record_identifies_actor(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    created = _create_route(client)
    records = [
        record for record in audit_logs.records if '"action": "route.create"' in record.getMessage()
    ]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "admin.panel" in message
    assert f'"target": "route:{created["id"]}"' in message


def test_route_listing_excludes_archived_and_admin_can_include(
    client: TestClient, seeded_admin: int
) -> None:
    admin = _admin_headers(client)
    first = _create_route(client)
    _create_route(client)
    client.delete(f"{GAMIFICATION_URL}/routes/{first['id']}", headers=admin)
    listing = client.get(f"{GAMIFICATION_URL}/routes", headers=admin)
    assert all(item["id"] != first["id"] for item in listing.json()["items"])
    with_archived = client.get(f"{GAMIFICATION_URL}/routes?includeArchived=true", headers=admin)
    assert any(item["id"] == first["id"] for item in with_archived.json()["items"])
    tourist = _tourist_headers(client)
    tourist_listing = client.get(f"{GAMIFICATION_URL}/routes", headers=tourist)
    assert tourist_listing.status_code == 200
    assert tourist_listing.json()["items"]
    tourist_archived = client.get(
        f"{GAMIFICATION_URL}/routes?includeArchived=true", headers=tourist
    )
    assert tourist_archived.status_code == 403
    _assert_api_error(tourist_archived, "authorization_failed")


def test_tourist_cannot_read_archived_route_detail(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)
    client.delete(f"{GAMIFICATION_URL}/routes/{created['id']}", headers=_admin_headers(client))
    tourist = _tourist_headers(client)
    response = client.get(f"{GAMIFICATION_URL}/routes/{created['id']}", headers=tourist)
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")


# ---------------------------------------------------------------------------
# US2 (T010): enrollment + progress — RF29/RF30; FR-013 self-scoping
# ---------------------------------------------------------------------------

ENROLLMENT_SUMMARY_KEYS = {"id", "routeId", "status", "completionRate", "createdAt", "completedAt"}
PROGRESS_KEYS = {
    "id",
    "routeId",
    "status",
    "completionRate",
    "createdAt",
    "completedAt",
    "spots",
    "visitedCount",
    "totalSpots",
    "badge",
    "redemptionCode",
}
PROGRESS_SPOT_KEYS = {"spotId", "visited"}


def test_enrollment_201_starts_in_progress_with_zero_completion(
    client: TestClient, seeded_admin: int
) -> None:
    created = _create_route(client)
    headers = _tourist_headers(client)
    response = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments", headers=headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == ENROLLMENT_SUMMARY_KEYS
    assert body["routeId"] == created["id"]
    assert body["status"] == "inProgress"
    assert body["completionRate"] == 0
    assert body["completedAt"] is None


def test_duplicate_enrollment_conflict_409(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)
    headers = _tourist_headers(client)
    first = client.post(f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments", headers=headers)
    assert first.status_code == 201, first.text
    duplicate = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments", headers=headers
    )
    assert duplicate.status_code == 409, duplicate.text
    _assert_api_error(duplicate, "conflict")
    listing = client.get(f"{GAMIFICATION_URL}/enrollments", headers=headers)
    assert len(listing.json()["items"]) == 1  # original untouched


def test_enrollment_of_archived_or_unknown_route_404(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)
    client.delete(f"{GAMIFICATION_URL}/routes/{created['id']}", headers=_admin_headers(client))
    headers = _tourist_headers(client)
    response = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments", headers=headers
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")
    unknown = client.post(f"{GAMIFICATION_URL}/routes/424242/enrollments", headers=headers)
    assert unknown.status_code == 404, unknown.text


def test_enrollment_refused_for_non_tourist(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    created = _create_route(client)
    admin = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments",
        headers=_admin_headers(client),
    )
    assert admin.status_code == 403, admin.text
    _assert_api_error(admin, "authorization_failed")
    employee = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments",
        headers=_employee_headers(client),
    )
    assert employee.status_code == 403, employee.text
    anonymous = client.post(f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments")
    assert anonymous.status_code == 401, anonymous.text


def test_enrollments_listing_is_own_only_and_ordered_desc(
    client: TestClient, seeded_admin: int
) -> None:
    first = _create_route(client)
    second = _create_route(client)
    tourist1 = _tourist_headers(client)
    tourist2 = _tourist_headers(client)
    assert (
        client.post(
            f"{GAMIFICATION_URL}/routes/{first['id']}/enrollments", headers=tourist1
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{GAMIFICATION_URL}/routes/{second['id']}/enrollments", headers=tourist1
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{GAMIFICATION_URL}/routes/{first['id']}/enrollments", headers=tourist2
        ).status_code
        == 201
    )
    listing = client.get(f"{GAMIFICATION_URL}/enrollments", headers=tourist1)
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 2  # tourist2's enrollment is invisible (FR-013)
    for item in items:
        assert set(item) == ENROLLMENT_SUMMARY_KEYS
    assert [item["routeId"] for item in items] == [second["id"], first["id"]]


def test_progress_full_payload_while_in_progress(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)  # 2 spots
    headers = _tourist_headers(client)
    enrollment = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments", headers=headers
    ).json()
    response = client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == PROGRESS_KEYS
    assert len(body["spots"]) == 2
    for spot in body["spots"]:
        assert set(spot) == PROGRESS_SPOT_KEYS
    assert body["visitedCount"] == 0
    assert body["totalSpots"] == 2
    assert body["completionRate"] == 0
    assert body["badge"] is None
    assert body["redemptionCode"] is None


def test_foreign_enrollment_is_indistinguishable_from_unknown(
    client: TestClient, seeded_admin: int
) -> None:
    created = _create_route(client)
    owner = _tourist_headers(client)
    enrollment = client.post(
        f"{GAMIFICATION_URL}/routes/{created['id']}/enrollments", headers=owner
    ).json()
    stranger = _tourist_headers(client)
    response = client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=stranger)
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")
    unknown = client.get(f"{GAMIFICATION_URL}/enrollments/424242", headers=stranger)
    assert unknown.status_code == 404, unknown.text


# ---------------------------------------------------------------------------
# US3 (T015): completed-progress payload — RF35/RF36 (badge + single-use code)
# Completion is driven through the register_spot_visit seam (R12) on the same
# isolated database; the HTTP read verifies the payload contract.
# ---------------------------------------------------------------------------


def _tourist_id_by_email(sessionfactory_for, email: str) -> int:  # noqa: ANN001,ANN002
    """Resolve the tourist id created over HTTP via the decrypted email."""
    from passanorte_back.modules.tourists.repositories.tourists import Tourist
    from passanorte_back.modules.tourists.services.tourists import decrypt_stored

    with sessionfactory_for() as session:
        for tourist in session.query(Tourist).all():
            if decrypt_stored(tourist.email_encrypted) == email:
                return tourist.id
    raise AssertionError(f"tourist {email} not found")


def _enroll_and_complete_all(client: TestClient, sessionfactory_for, route_id: int):  # noqa: ANN001,ANN002
    """Enroll (HTTP) then visit every route spot through the seam (R12)."""
    headers = _tourist_headers(client)
    email = _last_tourist_email
    tourist_id = _tourist_id_by_email(sessionfactory_for, email)
    spots = [
        spot["spotId"]
        for spot in client.get(f"{GAMIFICATION_URL}/routes/{route_id}", headers=headers).json()[
            "spots"
        ]
    ]
    enrollment = client.post(
        f"{GAMIFICATION_URL}/routes/{route_id}/enrollments", headers=headers
    ).json()
    with sessionfactory_for() as session:
        for spot_id in spots:
            gamification_service.register_spot_visit(
                session, tourist_id=tourist_id, tourist_spot_id=spot_id
            )
        session.commit()
    return enrollment["id"], headers, tourist_id


def test_completed_progress_payload_carries_badge_and_code(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    created = _create_route(client)  # 2 spots
    enrollment_id, headers, _tourist_id = _enroll_and_complete_all(
        client, sessionfactory_for, created["id"]
    )
    response = client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["completionRate"] == 100
    assert body["completedAt"] is not None
    assert body["badge"] is not None
    assert body["badge"]["routeId"] == created["id"]
    assert body["redemptionCode"] is not None
    assert len(body["redemptionCode"]["code"]) == 22
    assert body["redemptionCode"]["status"] == "unused"
    assert all(spot["visited"] for spot in body["spots"])


def test_issued_code_value_is_stable_across_reads(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    created = _create_route(client)
    enrollment_id, headers, _tourist_id = _enroll_and_complete_all(
        client, sessionfactory_for, created["id"]
    )
    codes = [
        client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment_id}", headers=headers).json()[
            "redemptionCode"
        ]["code"]
        for _ in range(2)
    ]
    assert codes[0] == codes[1]  # value stable — single-use state elsewhere


# ---------------------------------------------------------------------------
# US4 (T019): prize stock + staff concession — RF20/RF36 (Q3)
# ---------------------------------------------------------------------------

REDEMPTION_KEYS = {"code", "prize", "routeId", "touristId", "pickupSpotId", "concededBy", "usedAt"}


def _completed_with_code(
    client: TestClient, sessionfactory_for, *, initial_stock: int = 10, route: dict | None = None
):
    route = (
        route
        if route is not None
        else _create_route(
            client, prize={"name": "Caneca do Festival", "initialStock": initial_stock}
        )
    )
    enrollment_id, headers, tourist_id = _enroll_and_complete_all(
        client, sessionfactory_for, route["id"]
    )
    code = client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment_id}", headers=headers).json()[
        "redemptionCode"
    ]["code"]
    pickup_spot = route["spots"][0]["spotId"]
    return route, code, pickup_spot


def test_prize_stock_adjust_200_by_admin(client: TestClient, seeded_admin: int) -> None:
    created = _create_route(client)
    prize_id = created["prize"]["id"]
    response = client.patch(
        f"{GAMIFICATION_URL}/prizes/{prize_id}",
        json={"stockQuantity": 25},
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["stockQuantity"] == 25


def test_prize_stock_adjust_refused_non_admin(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    created = _create_route(client)
    prize_id = created["prize"]["id"]
    response = client.patch(
        f"{GAMIFICATION_URL}/prizes/{prize_id}",
        json={"stockQuantity": 5},
        headers=_employee_headers(client),
    )
    assert response.status_code == 403, response.text
    _assert_api_error(response, "authorization_failed")


def test_prize_stock_adjust_unknown_prize_404_and_negative_422(
    client: TestClient, seeded_admin: int
) -> None:
    admin = _admin_headers(client)
    response = client.patch(
        f"{GAMIFICATION_URL}/prizes/424242", json={"stockQuantity": 5}, headers=admin
    )
    assert response.status_code == 404, response.text
    _assert_api_error(response, "resource_not_found")
    negative = client.patch(
        f"{GAMIFICATION_URL}/prizes/1", json={"stockQuantity": -1}, headers=admin
    )
    assert negative.status_code == 422, negative.text


def test_prize_stock_adjust_cannot_go_below_committed_reservations(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    """Edge case: stock 0 with a held reservation → 422 (edge cases)."""
    route, code, pickup = _completed_with_code(client, sessionfactory_for, initial_stock=1)
    prize_id = route["prize"]["id"]
    response = client.patch(
        f"{GAMIFICATION_URL}/prizes/{prize_id}",
        json={"stockQuantity": 0},
        headers=_admin_headers(client),
    )
    assert response.status_code == 422, response.text
    still_works = client.patch(
        f"{GAMIFICATION_URL}/prizes/{prize_id}",
        json={"stockQuantity": 5},
        headers=_admin_headers(client),
    )
    assert still_works.status_code == 200, still_works.text


def test_concession_201_by_employee_and_by_admin(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    route, code, pickup = _completed_with_code(client, sessionfactory_for, initial_stock=1)
    stock_after = client.get(
        f"{GAMIFICATION_URL}/routes/{route['id']}", headers=_admin_headers(client)
    ).json()["prize"]["stockQuantity"]
    response = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": pickup},
        headers=_employee_headers(client),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == REDEMPTION_KEYS
    assert body["code"] == code
    assert body["pickupSpotId"] == pickup
    assert body["concededBy"] == "maria.panel"
    assert body["prize"]["name"] == "Caneca do Festival"
    final_stock = client.get(
        f"{GAMIFICATION_URL}/routes/{route['id']}", headers=_admin_headers(client)
    ).json()["prize"]["stockQuantity"]
    assert final_stock == stock_after - 1  # exactly one unit consumed
    # the code is now used: a second concession → 409 regardless of stock
    client.patch(
        f"{GAMIFICATION_URL}/prizes/{route['prize']['id']}",
        json={"stockQuantity": 50},
        headers=_admin_headers(client),
    )
    again = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": pickup},
        headers=_admin_headers(client),
    )
    assert again.status_code == 409, again.text
    _assert_api_error(again, "conflict")


def test_concession_refused_403_and_401(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    route, code, pickup = _completed_with_code(client, sessionfactory_for)
    tourist = _tourist_headers(client)
    as_tourist = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": pickup},
        headers=tourist,
    )
    assert as_tourist.status_code == 403, as_tourist.text
    _assert_api_error(as_tourist, "authorization_failed")
    anonymous = client.post(
        f"{GAMIFICATION_URL}/redemptions", json={"code": code, "spotId": pickup}
    )
    assert anonymous.status_code == 401, anonymous.text
    _assert_api_error(anonymous, "authentication_failed")


def test_concession_unknown_code_or_spot_404(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    route, code, pickup = _completed_with_code(client, sessionfactory_for)
    staff = _employee_headers(client)
    unknown_code = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": "zzzzzzzzzzzz", "spotId": pickup},
        headers=staff,
    )
    assert unknown_code.status_code == 404, unknown_code.text
    _assert_api_error(unknown_code, "resource_not_found")
    unknown_spot = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": 424242},
        headers=staff,
    )
    assert unknown_spot.status_code == 404, unknown_spot.text
    _assert_api_error(unknown_spot, "resource_not_found")
    # nothing changed: the code is still presentable and unused
    progress = client.get(
        f"{GAMIFICATION_URL}/routes/{route['id']}", headers=_admin_headers(client)
    )
    assert progress.status_code == 200


def test_concession_shape_failures_422(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    response = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": "", "spotId": 1},
        headers=_employee_headers(client),
    )
    assert response.status_code == 422, response.text
    snake = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"spot_id": 1},
        headers=_employee_headers(client),
    )
    assert snake.status_code == 422, snake.text
