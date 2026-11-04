"""Unit: events public seam ``list_upcoming_event_dates`` (feature 013, T005).

The discovery feed ranks spots by their nearest future event. The seam is
the events domain's read interface (constitution rule 3): one indexed query
on ``occurrence_date >= from_date``, ordered ``(occurrence_date, id)``,
reduced to the nearest future date per spot. Past events never appear;
a spot with no future events never appears; unknown/removed spot ids are
not special-cased here (the caller filters on spots).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from tests.conftest import sessionfactory_for  # noqa: F401


def _seed(
    session: Session,
    factory: sessionfactory_for,
    spot_id: int,
    days_offset: int,  # noqa: ARG001
) -> None:
    from passanorte_back.modules.events.repositories.events import Event

    session.add(
        Event(
            spot_id=spot_id,
            occurrence_date=date.today() + timedelta(days=days_offset),
            description="synthetic event",
            ticket_price_cents=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()


def _spot(session: Session, name: str, latitude: float, longitude: float) -> int:
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import add_spot

    return add_spot(session, name=name, description="d", latitude=latitude, longitude=longitude).id


def test_nearest_future_event_per_spot(sessionfactory_for) -> None:  # noqa: F811
    from passanorte_back.modules.events.services.events import list_upcoming_event_dates

    with sessionfactory_for() as session:
        near = _spot(session, "Near", -22.70, -45.00)
        far = _spot(session, "Far", -22.80, -45.10)
        _seed(session, sessionfactory_for, near, 7)
        _seed(session, sessionfactory_for, near, 20)  # farther future, same spot
        _seed(session, sessionfactory_for, far, 45)

        pairs = dict(list_upcoming_event_dates(session, from_date=date.today()))
        assert pairs[near] == date.today() + timedelta(days=7)
        assert pairs[far] == date.today() + timedelta(days=45)


def test_past_events_are_excluded(sessionfactory_for) -> None:  # noqa: F811
    from passanorte_back.modules.events.services.events import list_upcoming_event_dates

    with sessionfactory_for() as session:
        spot = _spot(session, "OnlyPast", -22.71, -45.01)
        _seed(session, sessionfactory_for, spot, -5)  # past
        _seed(session, sessionfactory_for, spot, -1)  # past

        assert list_upcoming_event_dates(session, from_date=date.today()) == []


def test_no_events_is_empty_not_error(sessionfactory_for) -> None:  # noqa: F811
    from passanorte_back.modules.events.services.events import list_upcoming_event_dates

    with sessionfactory_for() as session:
        assert list_upcoming_event_dates(session, from_date=date.today()) == []


def test_today_boundary_is_included(sessionfactory_for) -> None:  # noqa: F811
    from passanorte_back.modules.events.services.events import list_upcoming_event_dates

    with sessionfactory_for() as session:
        spot = _spot(session, "Today", -22.72, -45.02)
        _seed(session, sessionfactory_for, spot, 0)  # today counts as future

        pairs = dict(list_upcoming_event_dates(session, from_date=date.today()))
        assert pairs[spot] == date.today()
