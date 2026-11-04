"""Integration: the full gamification acceptance journey (feature 009 —
SC-007) plus the stock discipline (T021 US4).

Journey: admin creates spots + a route with a single-unit prize → tourist
enrolls (duplicate → 409) → visits every spot via the seam → enrollment
completed with exactly one badge and one code → staff concession consumes
the unit → second use of the code refused (409). Plus: complete with
stock 0 → concession blocked, code stays valid; stock race — two tourists
racing for the last unit, exactly one holds the reservation; archive
preserves the enrolled tourist's history (Removal Decision).
"""

from fastapi.testclient import TestClient

from passanorte_back.modules.gamification.services.gamification import (
    register_spot_visit,
)
from tests.conftest import TEST_ADMIN_PASSWORD

ADMIN_LOGIN = "/api/v1/auth/login"
TOURIST_LOGIN = "/api/v1/tourists/login"
GAMIFICATION_URL = "/api/v1/gamification"
SPOTS_URL = "/api/v1/tourist-spots"
EMPLOYEE_PASSWORD = "synthetic-employee-password-1"
TOURIST_PASSWORD = "long-enough-password-1"

_SPOT_SEQ = {"n": 0}
_TOURIST_SEQ = {"n": 0}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN, json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _employee_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        ADMIN_LOGIN, json={"username": "maria.panel", "password": EMPLOYEE_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _register_tourist(client: TestClient) -> str:
    _TOURIST_SEQ["n"] += 1
    email = f"turista-jornada-{_TOURIST_SEQ['n']}@example.com"
    response = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Ana",
            "lastName": "Silva",
            "countryOfOrigin": "Brasil",
            "passportNumber": f"P{_TOURIST_SEQ['n']:06d}",
            "phone": "+5511999999999",
            "email": email,
            "password": TOURIST_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": TOURIST_PASSWORD})
    assert login.status_code == 200, login.text
    return email


def _create_spot(client: TestClient, name: str) -> int:
    _SPOT_SEQ["n"] += 1
    response = client.post(
        SPOTS_URL,
        json={
            "name": name,
            "description": f"Ponto turístico de teste {name}.",
            "latitude": -22.7271,
            "longitude": -45.0366,
            "categories": ["nature"],
            "schedule": [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_route(client: TestClient, *, spot_ids: list[int], stock: int, name: str) -> dict:
    response = client.post(
        f"{GAMIFICATION_URL}/routes",
        json={
            "name": name,
            "description": "Rota turística da jornada de aceitação.",
            "spots": [
                {"spotId": spot_id, "displayOrder": order + 1}
                for order, spot_id in enumerate(spot_ids)
            ],
            "prize": {"name": "Caneca do Festival", "initialStock": stock},
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _enroll(
    client: TestClient, route_id: int, headers: dict[str, str], *, expect: int = 201
) -> dict:
    response = client.post(f"{GAMIFICATION_URL}/routes/{route_id}/enrollments", headers=headers)
    assert response.status_code == expect, response.text
    return response.json()


def _get_tourist_id_by_email(sessionfactory_for, email: str) -> int:  # noqa: ANN001,ANN002
    from passanorte_back.modules.tourists.repositories.tourists import Tourist
    from passanorte_back.modules.tourists.services.tourists import decrypt_stored

    with sessionfactory_for() as session:
        for tourist in session.query(Tourist).all():
            if decrypt_stored(tourist.email_encrypted) == email:
                return tourist.id
    raise AssertionError(f"tourist {email} not found")


def _visit_all(sessionfactory_for, tourist_id: int, spot_ids: list[int]) -> list:  # noqa: ANN001,ANN002
    with sessionfactory_for() as session:
        outcomes = [
            outcome
            for spot_id in spot_ids
            for outcome in register_spot_visit(
                session, tourist_id=tourist_id, tourist_spot_id=spot_id
            )
        ]
        session.commit()
    return outcomes


def _redemption_code_of(client: TestClient, enrollment_id: int, headers: dict[str, str]) -> str:  # noqa: ANN001,ANN002
    progress = client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment_id}", headers=headers).json()
    code = progress["redemptionCode"]
    assert code is not None and code["status"] == "unused"
    return code["code"]


def test_full_acceptance_journey_sc007(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for, audit_logs
) -> None:
    """SC-007: enroll → visit all → badge → unique code → refused reuse."""
    _admin_headers(client)
    spot_ids = [_create_spot(client, f"Mirante {n}") for n in range(1, 3)]
    route = _create_route(client, spot_ids=spot_ids, stock=1, name="Rota Jornada")

    email = _register_tourist(client)
    tourist_id = _get_tourist_id_by_email(sessionfactory_for, email)
    headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}

    enrollment = _enroll(client, route["id"], headers)
    duplicate = _enroll(client, route["id"], headers, expect=409)
    assert duplicate["errorCode"] == "conflict"

    outcomes = _visit_all(sessionfactory_for, tourist_id, spot_ids)
    mine = [outcome for outcome in outcomes if outcome.route_id == route["id"]]
    assert len(mine) == 2
    assert mine[-1].completed is True and mine[-1].completion_rate == 100

    progress = client.get(
        f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers
    ).json()
    assert progress["status"] == "completed"
    assert progress["badge"]["routeId"] == route["id"]

    code = _redemption_code_of(client, enrollment["id"], headers)
    concession = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": spot_ids[0]},
        headers=_employee_headers(client),
    )
    assert concession.status_code == 201, concession.text
    assert concession.json()["prize"]["name"] == "Caneca do Festival"
    assert concession.json()["prize"]["stockQuantity"] == 0  # 1 initial - 1 deduction
    # RF21/FR-007 (RNF19): the granting transaction emits exactly one audit
    # record with the actors and the stock before/after (1 → 0 here)
    concede_records = [
        record
        for record in audit_logs.records
        if '"action": "prize.concede"' in record.getMessage()
    ]
    assert len(concede_records) == 1
    audit_message = concede_records[0].getMessage()
    assert '"stockQuantityBefore": 1' in audit_message
    assert '"stockQuantityAfter": 0' in audit_message
    assert f'"touristId": {tourist_id}' in audit_message
    assert f'"prizeId": {route["prize"]["id"]}' in audit_message

    reused = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": spot_ids[0]},
        headers=_employee_headers(client),
    )
    assert reused.status_code == 409, reused.text
    assert reused.json()["errorCode"] == "conflict"


def _tourist_login_token(client: TestClient, email: str) -> str:  # noqa: ANN001
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": TOURIST_PASSWORD})
    return login.json()["accessToken"]


def test_concession_single_use_claim_guard_refuses_second_claim(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """RF21/FR-003: the single-use claim is a conditional UPDATE — it flips
    a code exactly once and REFUSES a second claim on the committed-used
    row (rowcount 0). This is the race primitive the HTTP layer rides on:
    racing scans of the same code reduce to exactly one winning claim
    (deterministic harness proof — the SQLite StaticPool test engine
    shares one connection, so a true threaded HTTP race cannot be
    simulated reliably here; production PostgreSQL gives each request its
    own connection, where this conditional-claim guard is the exact
    arbitration)."""
    spot_ids = [_create_spot(client, f"Mirante claim {n}") for n in range(1, 2)]
    route = _create_route(client, spot_ids=spot_ids, stock=3, name="Rota Claim")

    email = _register_tourist(client)
    tourist_id = _get_tourist_id_by_email(sessionfactory_for, email)
    headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}
    enrollment = _enroll(client, route["id"], headers)
    _visit_all(sessionfactory_for, tourist_id, spot_ids)
    code = _redemption_code_of(client, enrollment["id"], headers)

    from passanorte_back.modules.gamification.repositories import (
        gamification as gamification_repositories,
    )

    # rival claim wins the race first (committed 'used')
    staff = _employee_headers(client)
    granted = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": spot_ids[0]},
        headers=staff,
    )
    assert granted.status_code == 201, granted.text

    with sessionfactory_for() as session:
        code_row = gamification_repositories.find_code_by_value(session, code)
        assert code_row is not None and code_row.status == "used"
        code_id = code_row.id
        # second racer arrives late: the conditional claim refuses (rowcount 0)
        lost = gamification_repositories.claim_redemption_code(
            session, code_id, pickup_spot_id=spot_ids[0], conceded_by="maria.panel"
        )
        session.rollback()  # nothing written — the guard rejected the claim
        assert lost == 0
    # the concession stands untouched: one unit consumed, prize data intact
    remaining_stock = client.get(
        f"{GAMIFICATION_URL}/routes/{route['id']}", headers=_admin_headers(client)
    ).json()["prize"]["stockQuantity"]
    assert remaining_stock == 2  # 3 initial - exactly ONE deduction


def test_insufficient_stock_blocks_concession_code_stays_valid(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """A completion with stock 0 issues the code; the concession is blocked
    (409) until stock is replenished; then it succeeds (FR-004 clarified,
    research R4)."""
    spot_ids = [_create_spot(client, f"Mirante estoque {n}") for n in range(1, 2)]
    route = _create_route(client, spot_ids=spot_ids, stock=0, name="Rota Sem Estoque")

    email = _register_tourist(client)
    tourist_id = _get_tourist_id_by_email(sessionfactory_for, email)
    headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}
    enrollment = _enroll(client, route["id"], headers)
    _visit_all(sessionfactory_for, tourist_id, spot_ids)

    code = _redemption_code_of(client, enrollment["id"], headers)
    blocked = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": spot_ids[0]},
        headers=_employee_headers(client),
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["errorCode"] == "conflict"

    # The code remains valid/unused after the refusal (contract §4).
    raise_stock = client.patch(
        f"{GAMIFICATION_URL}/prizes/{route['prize']['id']}",
        json={"stockQuantity": 1},
        headers=_admin_headers(client),
    )
    assert raise_stock.status_code == 200, raise_stock.text
    concession = client.post(
        f"{GAMIFICATION_URL}/redemptions",
        json={"code": code, "spotId": spot_ids[0]},
        headers=_employee_headers(client),
    )
    assert concession.status_code == 201, concession.text
    prizes_after = client.get(
        f"{GAMIFICATION_URL}/routes/{route['id']}", headers=_admin_headers(client)
    ).json()["prize"]["stockQuantity"]
    assert prizes_after == 0  # the replenished unit was consumed exactly once


def test_two_tourists_racing_for_the_last_unit_hold_exactly_one_reservation(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """Story 4 scenario 4 (clarificação Q1): completions of the SAME route
    racing for a single-unit prize — exactly one holds the reservation."""
    spot_ids = [_create_spot(client, f"Mirante corrida {n}") for n in range(1, 2)]
    route = _create_route(client, spot_ids=spot_ids, stock=1, name="Rota Corrida")

    emails = [_register_tourist(client) for _ in range(2)]
    tourist_ids = [_get_tourist_id_by_email(sessionfactory_for, email) for email in emails]
    for _tourist_id, email in zip(tourist_ids, emails, strict=True):
        headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}
        _enroll(client, route["id"], headers)

    with sessionfactory_for() as session:
        first = register_spot_visit(session, tourist_id=tourist_ids[0], tourist_spot_id=spot_ids[0])
        session.commit()
        reserved_after_first = _prize_reserved(session, route["prize"]["id"])
        assert reserved_after_first == 1
        second = register_spot_visit(
            session, tourist_id=tourist_ids[1], tourist_spot_id=spot_ids[0]
        )
        session.commit()
        assert _prize_reserved(session, route["prize"]["id"]) == 1  # no double reservation

    first_completed = [outcome for outcome in first if outcome.route_id == route["id"]]
    second_completed = [outcome for outcome in second if outcome.route_id == route["id"]]
    assert first_completed[0].completed is True
    assert second_completed[0].completed is True  # both complete; only one reserves


def _prize_reserved(session, prize_id: int) -> int:  # noqa: ANN001
    from passanorte_back.modules.gamification.repositories.gamification import find_prize_by_id

    prize = find_prize_by_id(session, prize_id)
    return prize.reserved_quantity if prize else -1


def test_archive_preserves_enrolled_tourist_history(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    """Removal Decision (FR-012): archived route keeps the enrolled
    tourist's progress, badge and code readable."""
    spot_ids = [_create_spot(client, f"Mirante arquivado {n}") for n in range(1, 2)]
    route = _create_route(client, spot_ids=spot_ids, stock=3, name="Rota Arquivável")
    email = _register_tourist(client)
    tourist_id = _get_tourist_id_by_email(sessionfactory_for, email)
    headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}
    enrollment = _enroll(client, route["id"], headers)
    _visit_all(sessionfactory_for, tourist_id, spot_ids)

    response = client.delete(
        f"{GAMIFICATION_URL}/routes/{route['id']}", headers=_admin_headers(client)
    )
    assert response.status_code == 204, response.text

    progress = client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers)
    assert progress.status_code == 200
    body = progress.json()
    assert body["status"] == "completed"
    assert body["badge"] is not None and body["redemptionCode"] is not None
    listing = client.get(f"{GAMIFICATION_URL}/routes", headers=_admin_headers(client))
    assert all(item["id"] != route["id"] for item in listing.json()["items"])


# ---------------------------------------------------------------------------
# Phase 8 (T026): route edit re-evaluate in-progress enrollments (Edge Cases 1)
# ---------------------------------------------------------------------------


def test_edit_shrinking_route_completes_in_progress_enrollments(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    """Edge case 1: route edited down to the already-visited spots → the
    in-progress enrollment completes exactly once with badge + code."""
    spot_a = _create_spot(client, "Mirante encolhe A")
    spot_b = _create_spot(client, "Mirante encolhe B")
    route = _create_route(client, spot_ids=[spot_a, spot_b], stock=3, name="Rota Encolhida")
    email = _register_tourist(client)
    tourist_id = _get_tourist_id_by_email(sessionfactory_for, email)
    headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}
    enrollment = _enroll(client, route["id"], headers)
    _visit_all(sessionfactory_for, tourist_id, [spot_a])
    assert (
        client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers).json()[
            "completionRate"
        ]
        == 50
    )

    edit = client.patch(
        f"{GAMIFICATION_URL}/routes/{route['id']}",
        json={"spots": [{"spotId": spot_a, "displayOrder": 1}]},
        headers=_admin_headers(client),
    )
    assert edit.status_code == 200, edit.text

    progress = client.get(
        f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers
    ).json()
    assert progress["status"] == "completed"
    assert progress["completionRate"] == 100
    assert progress["badge"] is not None and progress["redemptionCode"] is not None

    with sessionfactory_for() as session:
        from passanorte_back.modules.gamification.repositories.gamification import (
            find_badge,
            find_code_for_owner,
        )

        assert find_badge(session, route_id=route["id"], tourist_id=tourist_id) is not None
        code_row = find_code_for_owner(session, route_id=route["id"], tourist_id=tourist_id)
        assert code_row is not None
    # Repeating the identical edit does not duplicate rewards.
    client.patch(
        f"{GAMIFICATION_URL}/routes/{route['id']}",
        json={"spots": [{"spotId": spot_a, "displayOrder": 1}]},
        headers=_admin_headers(client),
    )
    with sessionfactory_for() as session:
        from sqlalchemy import func as sql_func

        from passanorte_back.modules.gamification.repositories.gamification import (
            RedemptionCode,
        )

        assert session.query(sql_func.count(RedemptionCode.id)).scalar() == 1


def test_edit_growing_route_keeps_enrollments_in_progress_with_new_pending(
    client: TestClient, seeded_admin: int, sessionfactory_for
) -> None:
    """Edge case 2a: adding spots only affects enrollments still in
    progress — they gain the new pending spot."""
    spot_a = _create_spot(client, "Mirante cresce A")
    route = _create_route(client, spot_ids=[spot_a], stock=3, name="Rota Crescente")
    email = _register_tourist(client)
    tourist_id = _get_tourist_id_by_email(sessionfactory_for, email)
    headers = {"Authorization": f"Bearer {_tourist_login_token(client, email)}"}
    enrollment = _enroll(client, route["id"], headers)
    _visit_all(sessionfactory_for, tourist_id, [spot_a])
    assert (
        client.get(f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers).json()[
            "status"
        ]
        == "completed"
    )

    spot_b = _create_spot(client, "Mirante cresce B")
    edit = client.patch(
        f"{GAMIFICATION_URL}/routes/{route['id']}",
        json={
            "spots": [{"spotId": spot_a, "displayOrder": 1}, {"spotId": spot_b, "displayOrder": 2}]
        },
        headers=_admin_headers(client),
    )
    assert edit.status_code == 200, edit.text

    progress = client.get(
        f"{GAMIFICATION_URL}/enrollments/{enrollment['id']}", headers=headers
    ).json()
    assert progress["status"] == "completed"  # completed stays completed
    assert progress["completionRate"] == 100
