"""Integration: the visitation mark → status → route-progress flow (feature 011).

T013 US1 (immutable record), T016 US2 (structured rejection log, per-spot
override), T017 US3 (RF34 via the spec 009 public seam), T019 US3 (repeat
idempotency — progress counted exactly once). The gamification side is
seeded through its public services only (same pattern as
``tests/integration/test_gamification_visit.py``); visitation never touches
gamification internals (SC-005). Tourist tokens come from the real login
flow; the tourist id doubles as the auth account id (R7).
"""

import logging

from fastapi.testclient import TestClient
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from passanorte_back.modules.gamification import schemas as gamification_schemas
from passanorte_back.modules.gamification.repositories.gamification import (
    CompletionBadge,
    RedemptionCode,
    RouteEnrollment,
    SpotVisit,
)
from passanorte_back.modules.gamification.services.gamification import (
    create_route,
    enroll_tourist,
)
from passanorte_back.modules.tourist_spots import schemas as spot_schemas
from passanorte_back.modules.tourist_spots.services.tourist_spots import create_spot
from passanorte_back.modules.tourists.services.tourists import register_tourist
from passanorte_back.modules.visitation.repositories.visitations import Visitation

TOURIST_PASSWORD = "long-enough-password-1"
SPOT_ANCHOR = (-22.7271, -45.0366)
_EMAIL_COUNTER = [0]


def _unique_email() -> str:
    _EMAIL_COUNTER[0] += 1
    return f"visita-{_EMAIL_COUNTER[0]}@example.com"


def _create_spot(session: Session, radius: float | None = None) -> int:
    """ApiModel is strict by alias — programmatic construction with snake_case
    multi-word fields must go through ``from_internal`` (spec 005 FR-002)."""
    payload = spot_schemas.SpotCreateRequest.from_internal(
        name="Mirante Pedra do Bauzinho",
        description="Mirante com vista para o vale e trilha curta.",
        latitude=SPOT_ANCHOR[0],
        longitude=SPOT_ANCHOR[1],
        tolerance_radius_m=radius,
        categories=["nature"],
        schedule=[{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
    )
    return create_spot(session, actor="admin.panel", payload=payload).id


def _seed_tourist(session: Session) -> tuple[int, str]:
    """Register via the tourists public service; return (tourist_id, email)."""
    email = _unique_email()
    tourist = register_tourist(
        session,
        first_name="Ana",
        last_name="Silva",
        country_of_origin="Brasil",
        normalized_email=email,
        phone="+5511999999999",
        password=TOURIST_PASSWORD,
    )
    return tourist.id, email


def _seed_route(session: Session, tourist_id: int, spots: list[int]) -> int:
    """Enroll the tourist in a route over ``spots`` (in-progress)."""
    route = create_route(
        session,
        actor="admin.panel",
        payload=gamification_schemas.RouteCreateRequest(
            name="Rota do Vale",
            description="Dois mirantes e um presente.",
            spots=[
                {"spotId": spot_id, "displayOrder": order + 1}
                for order, spot_id in enumerate(spots)
            ],
            prize={"name": "Caneca do Vale", "initialStock": 5},
        ),
    )
    enroll_tourist(session, tourist_id=tourist_id, route_id=route.id)
    return route.id


def _mark(
    client: TestClient,
    token: str,
    spot_id: int,
    latitude: float,
    longitude: float,
):
    """POST the visitation through the real HTTP border."""
    return client.post(
        f"/api/v1/visitation/spots/{spot_id}/visits",
        json={"latitude": latitude, "longitude": longitude},
        headers={"Authorization": f"Bearer {token}"},
    )


def _login_token(client: TestClient, email: str) -> str:
    login = client.post(
        "/api/v1/tourists/login",
        json={"email": email, "password": TOURIST_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return login.json()["accessToken"]


# ---------------------------------------------------------------------------
# T013 US1: valid mark → 201 with the seam-less shape of its increment
# ---------------------------------------------------------------------------


def test_mark_inside_radius_persists_immutable_record(
    client: TestClient,
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        spot_id = _create_spot(session)  # no override ⇒ 100 m global default
        tourist_id, email = _seed_tourist(session)
        session.commit()
    token = _login_token(client, email)

    response = _mark(client, token, spot_id, -22.7266, SPOT_ANCHOR[1])  # ~55 m
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["firstVisit"] is True
    assert body["routeOutcomes"] == []  # US3 seeds its own route world
    assert body["spotId"] == spot_id
    assert body["latitude"] == -22.7266

    with sessionfactory_for() as session:
        row = (
            session.query(Visitation)
            .filter(
                Visitation.tourist_id == tourist_id,
                Visitation.tourist_spot_id == spot_id,
            )
            .one_or_none()
        )
        assert row is not None
        assert row.latitude == -22.7266  # validated coordinates persisted (SC-003)
        assert row.longitude == SPOT_ANCHOR[1]
        assert row.visited_at is not None  # timestamp — immutable row (SC-003)


# ---------------------------------------------------------------------------
# T016 US2: outside radius → 409, no row, exactly one structured warning log
# ---------------------------------------------------------------------------


def test_mark_outside_radius_409_no_row_one_structured_log(
    client: TestClient,
    sessionfactory_for,
    audit_logs,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        spot_id = _create_spot(session, radius=25.0)  # stricter per-spot override
        _tourist_id, email = _seed_tourist(session)
        session.commit()
    token = _login_token(client, email)

    # ~80 m away: inside the 100 m global default, outside the 25 m override.
    response = _mark(client, token, spot_id, -22.7264, SPOT_ANCHOR[1])
    assert response.status_code == 409, response.text
    assert response.json()["errorCode"] == "conflict"  # unified taxonomy (spec 005 §2)

    records = [
        record for record in audit_logs.records if "outside_tolerance_radius" in record.getMessage()
    ]
    assert len(records) == 1  # SC-007: one structured warning per rejection
    assert records[0].levelno == logging.WARNING


# ---------------------------------------------------------------------------
# T017 US3: first visit fires the seam; progress rises; completion exactly once
# ---------------------------------------------------------------------------


def test_first_visit_advances_route_progress_and_completion_once(
    client: TestClient,
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        tourist_id, email = _seed_tourist(session)
        spot_a = _create_spot(session)
        spot_b = _create_spot(session)
        _seed_route(session, tourist_id, [spot_a, spot_b])
        session.commit()
    token = _login_token(client, email)

    first = _mark(client, token, spot_a, -22.7266, SPOT_ANCHOR[1])
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["firstVisit"] is True
    outcomes = body["routeOutcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["completionRate"] == 50  # 1 of 2 spots (RF34)
    assert outcomes[0]["completed"] is False

    second = _mark(client, token, spot_b, -22.7266, SPOT_ANCHOR[1])
    assert second.status_code == 201, second.text
    second_outcomes = second.json()["routeOutcomes"]
    assert second_outcomes[0]["completionRate"] == 100  # last pending spot
    assert second_outcomes[0]["completed"] is True  # completed exactly once


# ---------------------------------------------------------------------------
# T019 US3: repeat appends to the immutable history without progress updates
# ---------------------------------------------------------------------------


def test_repeat_visit_is_recorded_but_progress_is_idempotent(
    client: TestClient,
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        tourist_id, email = _seed_tourist(session)
        spot_id = _create_spot(session)
        _seed_route(session, tourist_id, [spot_id])  # single-spot route
        session.commit()
    token = _login_token(client, email)

    first = _mark(client, token, spot_id, -22.7266, SPOT_ANCHOR[1])
    assert first.status_code == 201
    assert first.json()["firstVisit"] is True
    assert first.json()["routeOutcomes"][0]["completed"] is True  # single-spot route

    repeat = _mark(client, token, spot_id, -22.7265, SPOT_ANCHOR[1])
    assert repeat.status_code == 201, repeat.text
    assert repeat.json()["firstVisit"] is False
    assert repeat.json()["routeOutcomes"] == []  # FR-009: no new progress update

    with sessionfactory_for() as session:
        # Seam ledger: exactly one gamification visit for the pair.
        assert (
            session.query(SpotVisit)
            .filter(
                SpotVisit.tourist_id == tourist_id,
                SpotVisit.tourist_spot_id == spot_id,
            )
            .count()
            == 1
        )
        # Rewards emitted only for the single completion — never duplicated.
        assert session.query(sql_func.count(RedemptionCode.id)).scalar() == 1
        assert session.query(sql_func.count(CompletionBadge.id)).scalar() == 1
        assert (
            session.query(sql_func.count(RouteEnrollment.id))
            .filter(RouteEnrollment.tourist_id == tourist_id)
            .scalar()
            == 1
        )
        # Immutable visitation history: first + repeat (SC-003, FR-009).
        assert (
            session.query(Visitation)
            .filter(
                Visitation.tourist_id == tourist_id,
                Visitation.tourist_spot_id == spot_id,
            )
            .count()
            == 2
        )
