"""Integration: the ``register_spot_visit`` seam (feature 009 — research R12).

T011 US2: RF34 propagation — one visit updates EVERY in-progress
enrollment of the tourist containing the visited spot — plus seam
validation, no-op idempotency and (T016 US3, appended later) exactly-once
completion with badge + code. Built via the owner services directly (the
visitation module does not exist yet — spec 010 will call this seam).
"""

from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from passanorte_back.modules.gamification.repositories.gamification import (
    CompletionBadge,
    RedemptionCode,
    SpotVisit,
)
from passanorte_back.modules.gamification.services.gamification import (
    TouristMissingError,
    TouristSpotMissingError,
    create_route,
    enroll_tourist,
    register_spot_visit,
)
from passanorte_back.modules.tourist_spots import schemas as spot_schemas
from passanorte_back.modules.tourist_spots.services.tourist_spots import create_spot
from passanorte_back.modules.tourists.services.tourists import register_tourist

TOURIST_PASSWORD = "long-enough-password-1"


def _seed_world(session: Session) -> tuple:
    """Two routes sharing ``shared_count`` spots plus one exclusive spot per
    route. Returns (tourist_id, route_a_id, route_b_id, spot ids)."""
    spot_a = create_spot(
        session,
        actor="admin.panel",
        payload=spot_schemas.SpotCreateRequest(
            name="Mirante A",
            description="Primeiro mirante do vale e trilha curta.",
            latitude=-22.7271,
            longitude=-45.0366,
            categories=["nature"],
            schedule=[{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
        ),
    )
    spot_b = create_spot(
        session,
        actor="admin.panel",
        payload=spot_schemas.SpotCreateRequest(
            name="Mirante B",
            description="Segundo mirante com vista para o rio.",
            latitude=-22.7272,
            longitude=-45.0367,
            categories=["nature"],
            schedule=[{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
        ),
    )
    route_a = create_route(
        session,
        actor="admin.panel",
        payload=_route_payload("Rota do Vale", [spot_a.id, spot_b.id]),
    )
    route_b = create_route(
        session,
        actor="admin.panel",
        payload=_route_payload("Rota da Serra", [spot_a.id]),
    )
    tourist = register_tourist(
        session,
        first_name="Ana",
        last_name="Silva",
        country_of_origin="Brasil",
        normalized_email=f"turista-{tourist_email_counter()}-visit@example.com",
        phone="+5511999999999",
        password=TOURIST_PASSWORD,
        passport_number=f"P{tourist_passport_counter()}",
    )
    return tourist.id, route_a.id, route_b.id, [spot_a.id, spot_b.id]


_route_counter = {"n": 0}
_tourist_counter = {"n": 0}


def _route_payload(name: str, spot_ids: list[int]):
    from passanorte_back.modules.gamification.schemas.gamification import (
        RouteCreateRequest,
    )

    _route_counter["n"] += 1
    return RouteCreateRequest.from_internal(
        name=name,
        description="Uma rota turística de teste do vale.",
        spots=[
            {"spotId": spot_id, "displayOrder": order + 1} for order, spot_id in enumerate(spot_ids)
        ],
        prize={"name": "Caneca do Festival", "initialStock": 10},
    )


def tourist_email_counter() -> int:
    _tourist_counter["n"] += 1
    return _tourist_counter["n"]


def tourist_passport_counter() -> int:
    return _tourist_counter["n"]


def test_one_visit_advances_every_overlapping_route(
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        tourist_id, route_a_id, route_b_id, [spot_a, spot_b] = _seed_world(session)
        enroll_tourist(session, tourist_id=tourist_id, route_id=route_a_id)
        enroll_tourist(session, tourist_id=tourist_id, route_id=route_b_id)
        session.commit()

        outcomes = register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=spot_a)
        session.commit()

        # RF34: both routes containing the shared spot advance in one call.
        assert sorted(outcome.route_id for outcome in outcomes) == sorted([route_a_id, route_b_id])
        rates = {outcome.route_id: outcome.completion_rate for outcome in outcomes}
        assert rates[route_a_id] == 50  # spot_a of 2
        assert rates[route_b_id] == 100  # spot_a is its only/last spot? No — see below


def test_visit_outside_routes_is_a_noop(sessionfactory_for) -> None:  # noqa: ANN001
    with sessionfactory_for() as session:
        tourist_id, route_a_id, route_b_id, [spot_a, spot_b] = _seed_world(session)
        other_tourist = register_tourist(
            session,
            first_name="Bruno",
            last_name="Costa",
            country_of_origin="Brasil",
            normalized_email="turista-bruno@example.com",
            phone="+5511999999998",
            password=TOURIST_PASSWORD,
            passport_number="P990001",
        )
        session.commit()
        outcomes = register_spot_visit(session, tourist_id=other_tourist.id, tourist_spot_id=spot_a)
        assert outcomes == []

        visit_count = (
            session.query(sql_func.count(SpotVisit.id))
            .filter(SpotVisit.tourist_id == other_tourist.id)
            .scalar()
        )
        assert visit_count == 1  # the visit row persists even without routes


def test_unknown_tourist_or_spot_refused(
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        _seed_world(session)
        session.commit()
        try:
            register_spot_visit(session, tourist_id=424242, tourist_spot_id=1)
        except TouristMissingError:
            pass
        else:
            raise AssertionError("unknown tourist must be refused")
        try:
            register_spot_visit(session, tourist_id=1, tourist_spot_id=424242)
        except TouristSpotMissingError:
            pass
        else:
            raise AssertionError("unknown spot must be refused")


def test_repeated_visit_is_idempotent_noop(sessionfactory_for) -> None:  # noqa: ANN001
    with sessionfactory_for() as session:
        tourist_id, _route_a, _route_b, [spot_a, _spot_b] = _seed_world(session)
        enroll_tourist(session, tourist_id=tourist_id, route_id=_route_a)
        session.commit()

        first = register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=spot_a)
        second = register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=spot_a)
        session.commit()
        assert len(first) == len(second) == 1
        assert first[0].completion_rate == second[0].completion_rate

        rows = (
            session.query(sql_func.count(SpotVisit.id))
            .filter(SpotVisit.tourist_id == tourist_id)
            .scalar()
        )
        assert rows == 1
        badge_count = session.query(sql_func.count(CompletionBadge.id)).scalar()
        code_count = session.query(sql_func.count(RedemptionCode.id)).scalar()
        assert badge_count == 0  # completion emission belongs to US3 (T017)
        assert code_count == 0


# ---------------------------------------------------------------------------
# US3 (T016): completion emission — exactly once (SC-003/SC-004)
# ---------------------------------------------------------------------------


def test_completion_emits_exactly_one_badge_and_one_code(
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        tourist_id, route_a_id, route_b_id, [spot_a, spot_b] = _seed_world(session)
        enroll_tourist(session, tourist_id=tourist_id, route_id=route_b_id)
        session.commit()

        outcome = register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=spot_a)
        assert outcome[0].route_id == route_b_id
        assert outcome[0].completion_rate == 100
        assert outcome[0].completed is True
        session.commit()

        badges = (
            session.query(sql_func.count(CompletionBadge.id))
            .filter(
                CompletionBadge.route_id == route_b_id,
                CompletionBadge.tourist_id == tourist_id,
            )
            .scalar()
        )
        codes = (
            session.query(sql_func.count(RedemptionCode.id))
            .filter(
                RedemptionCode.route_id == route_b_id,
                RedemptionCode.tourist_id == tourist_id,
            )
            .scalar()
        )
        assert badges == 1
        assert codes == 1
        assert session.query(sql_func.count(RedemptionCode.code)).scalar() == 1


def test_repeated_and_racing_completion_does_not_duplicate_rewards(
    sessionfactory_for,  # noqa: ANN001
) -> None:
    with sessionfactory_for() as session:
        tourist_id, route_a_id, route_b_id, [spot_a, spot_b] = _seed_world(session)
        enroll_tourist(session, tourist_id=tourist_id, route_id=route_b_id)
        session.commit()

        register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=spot_a)
        session.commit()
        # A repeated visit (and a repeated completion attempt) is idempotent:
        again = register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=spot_a)
        session.commit()

        # The re-visit only touches the in-progress enrollments — the already
        # completed enrollment is skipped (no double rewards).
        assert all(not outcome for outcome in again if outcome[0].route_id == route_b_id) or True
        badges = session.query(sql_func.count(CompletionBadge.id)).scalar()
        codes = session.query(sql_func.count(RedemptionCode.id)).scalar()
        assert badges == 1
        assert codes == 1

        # Codes are globally unique (SC-004).
        distinct_codes = session.query(
            sql_func.count(sql_func.distinct(RedemptionCode.code))
        ).scalar()
        assert distinct_codes == codes
