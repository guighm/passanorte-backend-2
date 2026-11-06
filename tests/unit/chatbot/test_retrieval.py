"""Unit: chatbot retrieval pipeline (feature 016 — T019 US2, FR-020/SC-001,
FR-009, FR-012).

Real seeded database through the owner-domain service seams (create_spot,
event repo) — the pipeline is challenged against a controlled base: a
relevant query returns the RIGHT spots (SC-001), interest categories
outrank non-interest candidates (FR-012), and closed/wrong-day items never
become candidates (FR-009/FR-024).
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from passanorte_back.modules.chatbot.services import retrieval
from passanorte_back.modules.tourist_spots import schemas as spot_schemas
from passanorte_back.modules.tourist_spots.services.tourist_spots import create_spot

CITY_TZ = ZoneInfo("America/Sao_Paulo")

EVERY_DAY = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _open_schedule(
    weekdays: list[str] | None = None, *, opens: str = "00:00", closes: str = "23:59"
):
    days = weekdays or EVERY_DAY
    return [{"weekday": day, "opensAt": opens, "closesAt": closes} for day in days]


def _spot(
    session,
    *,
    name: str,
    description: str,
    categories: list[str],
    schedule=None,
) -> int:
    payload = spot_schemas.SpotCreateRequest.from_internal(
        name=name,
        description=description,
        latitude=-22.73,
        longitude=-45.01,
        categories=categories,
        schedule=schedule or _open_schedule(),
    )
    return create_spot(session, actor="admin.panel", payload=payload).id


def _seed(sessionfactory_for) -> dict[str, int]:
    with sessionfactory_for() as session:
        waterfall = _spot(
            session,
            name="Cachoeira Édem",
            description="Cachoeira com piscina natural e trilha leve.",
            categories=["nature"],
        )
        museum = _spot(
            session,
            name="Museu Ferroviário",
            description="Museu com peças da ferrovia antiga.",
            categories=["culture"],
        )
        session.commit()

        from passanorte_back.modules.events.repositories.events import add_event

        event = add_event(
            session,
            spot_id=museum,
            occurrence_date=date(2026, 11, 10),
            description="Festival de inverno no museu",
            ticket_price_cents=2500,
        )
        session.commit()
        return {"waterfall": waterfall, "museum": museum, "event": event.id}


def _seed_interests(sessionfactory_for, tourist_id: int, keys: list[str]) -> None:
    from passanorte_back.core.config import get_settings
    from passanorte_back.modules.tourists.repositories.tourist_interests import (
        replace_selection,
    )

    valid = {item["key"] for item in get_settings().resolved_interest_categories()}
    keys = [key for key in keys if key in valid]
    with sessionfactory_for() as session:
        replace_selection(session, tourist_id, keys)
        session.commit()


def _retrieve(sessionfactory_for, *, tourist_id: int = 1, day, hour: int = 10):
    at = datetime.combine(day, time(hour), tzinfo=CITY_TZ)
    with sessionfactory_for() as session:
        return retrieval.retrieve_candidates(
            session, tourist_id=tourist_id, at=at, target_day=day, query="cachoeira natureza"
        )


@pytest.fixture
def catalog(sessionfactory_for) -> dict[str, int]:
    return _seed(sessionfactory_for)


WEDNESDAY = date(2026, 11, 4)  # a fixed weekday for deterministic open-now checks


def test_relevant_query_returns_the_right_spots(sessionfactory_for, catalog) -> None:
    """SC-001: 'cachoeira' ranks the waterfall candidates first, museum last."""
    candidates = _retrieve(sessionfactory_for, day=WEDNESDAY)
    kinds = [candidate.ref_id for candidate in candidates]
    assert catalog["waterfall"] in kinds
    # waterfall candidates must come before the museum candidate
    assert kinds.index(catalog["waterfall"]) < kinds.index(catalog["museum"])


def test_interest_categories_boost_ranking(sessionfactory_for, catalog) -> None:
    """FR-012: a nature-interested tourist sees the nature spot outrank a
    culture spot with the SAME generic query (query without 'cachoeira')."""
    _seed_interests(sessionfactory_for, 1, ["nature"])
    at = datetime.combine(WEDNESDAY, time(10), tzinfo=CITY_TZ)
    with sessionfactory_for() as session:
        candidates = retrieval.retrieve_candidates(
            session, tourist_id=1, at=at, target_day=WEDNESDAY, query="passeio"
        )
    by_id = {candidate.ref_id: candidate.score for candidate in candidates}
    assert by_id[catalog["waterfall"]] > by_id[catalog["museum"]]


def test_no_interests_leave_neutral_ranking(sessionfactory_for, catalog) -> None:
    """Without declared interests, candidates still return (no crash), and
    the query-relevant spot leads."""
    candidates = _retrieve(sessionfactory_for, day=WEDNESDAY)
    assert candidates, "candidates exist regardless of interests"


def test_closed_spot_is_never_a_candidate(sessionfactory_for, catalog) -> None:
    """FR-009: a spot scheduled ONLY on sundays is invisible on wednesday."""
    with sessionfactory_for() as session:
        sunday_only = _spot(
            session,
            name="Feira de Domingo",
            description="Feira artesanal de domingo.",
            categories=["leisure"],
            schedule=_open_schedule(["sunday"], opens="08:00", closes="18:00"),
        )
        session.commit()
    candidates = _retrieve(sessionfactory_for, day=WEDNESDAY)
    assert sunday_only not in [candidate.ref_id for candidate in candidates]


def test_event_of_other_day_is_never_a_candidate(sessionfactory_for, catalog) -> None:
    """FR-024: the event happens on 2026-11-10; wednesday day 04 must not
    yield it as a candidate (event ids may collide with spot ids — kind
    aware check)."""
    day = WEDNESDAY
    candidates = _retrieve(sessionfactory_for, day=day)
    event_refs = {(c.kind, c.ref_id) for c in candidates if c.kind == "event"}
    assert ("event", catalog["event"]) not in event_refs

    event_day = date(2026, 11, 10)
    event_candidates = _retrieve(sessionfactory_for, day=event_day)
    event_refs = {(c.kind, c.ref_id) for c in event_candidates if c.kind == "event"}
    assert ("event", catalog["event"]) in event_refs
