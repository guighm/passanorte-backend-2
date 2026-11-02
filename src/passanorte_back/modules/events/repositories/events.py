"""Events persistence (feature 008 data-model §1; events module).

The ``events`` table belongs exclusively to this domain. ``spot_id`` is a
read-only reference into ``tourist_spots.id`` — it is written here only
after the events service validated the target through the tourist_spots
public service interface (research R3), and cascaded deletes are executed
here only when that module's public service asks for them (research R4).
Removal of an event is physical (hard delete): the cascade contract makes
events cease to exist together with their spot, so no soft-delete column
exists (research R9).
"""

from datetime import UTC, date, datetime
from typing import Final

from sqlalchemy import Date, ForeignKey, Integer, String, delete
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

DESCRIPTION_LENGTH: Final[int] = 2000
MAX_PRICE_CENTS: Final[int] = 999999999999  # contract TicketPrice max_digits=12


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Event(Base):
    """A scheduled occurrence attached to exactly one tourist spot."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    spot_id: Mapped[int] = mapped_column(
        ForeignKey("tourist_spots.id", ondelete="CASCADE"), index=True
    )
    occurrence_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(DESCRIPTION_LENGTH))
    ticket_price_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)


def add_event(
    session: Session,
    *,
    spot_id: int,
    occurrence_date: date,
    description: str,
    ticket_price_cents: int,
) -> Event:
    """Insert one validated event (service layer owns every rule)."""
    event = Event(
        spot_id=spot_id,
        occurrence_date=occurrence_date,
        description=description,
        ticket_price_cents=ticket_price_cents,
    )
    session.add(event)
    session.flush()
    return event


def find_event_by_id(session: Session, event_id: int) -> Event | None:
    """Active listing/read lookups — removed rows no longer exist."""
    return session.get(Event, event_id)


def list_events(
    session: Session,
    *,
    spot_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Event]:
    """Combined-filter listing (FR-007/FR-008): optional spot and/or
    inclusive date-range bounds, stable ``(occurrence_date, id)`` order.
    No pagination this version (spec 008 assumption)."""
    query = session.query(Event)
    if spot_id is not None:
        query = query.filter(Event.spot_id == spot_id)
    if start_date is not None:
        query = query.filter(Event.occurrence_date >= start_date)
    if end_date is not None:
        query = query.filter(Event.occurrence_date <= end_date)
    return list(query.order_by(Event.occurrence_date, Event.id).all())


def delete_event(session: Session, event: Event) -> None:
    """Physical removal of one event (FR-003)."""
    session.delete(event)
    session.flush()


def delete_spot_events(session: Session, spot_id: int) -> int:
    """Hard delete every event of a spot (cascade, research R4).

    Called exclusively through the events public service interface by
    ``tourist_spots.remove_spot`` in the same transaction. Returns the
    number of rows removed.
    """
    result = session.execute(delete(Event).where(Event.spot_id == spot_id))
    session.flush()
    return int(result.rowcount or 0)
