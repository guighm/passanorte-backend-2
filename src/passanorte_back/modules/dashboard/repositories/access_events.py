"""Access-event ledger of tourist requests (feature 014 — data-model.md §1).

The table and its data access belong exclusively to the ``dashboard``
domain: rows are appended by the recording middleware (services) and
consumed by the access-count aggregates (FR-007/FR-008). Insert-only —
no update/delete paths exist (immutability, spec FR-011). ``day`` is the
city-tz calendar day computed ONCE at write time (research R3), making
every aggregate a set-based SQL query (FR-020) riding the composite index
``ix_access_events_tourist_day``.
"""

from datetime import UTC, date, datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import Date, DateTime, ForeignKey, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.config import get_settings
from passanorte_back.core.db import Base


def city_tz() -> ZoneInfo:
    """City timezone (RNF06) — from configuration, never hardcoded."""
    return ZoneInfo(get_settings().resolved_city_timezone())


def city_day(moment: datetime) -> date:
    """City-tz calendar day of a UTC moment (FR-011 bucketing)."""
    return moment.astimezone(city_tz()).date()


class AccessEvent(Base):
    """One tourist-authenticated HTTP request (data-model.md §1)."""

    __tablename__ = "access_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(
        ForeignKey("tourists.id"), index=True
    )  # read-only tourists reference (constitution rule 4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC)
    )
    day: Mapped[date] = mapped_column(Date, index=True)


def add_access_event(
    session: Session, *, tourist_id: int, occurred_at: datetime | None = None
) -> AccessEvent:
    """Append one access event (occurred_at defaults to the current UTC)."""
    moment = occurred_at if occurred_at is not None else datetime.now(UTC)
    event = AccessEvent(tourist_id=tourist_id, occurred_at=moment, day=city_day(moment))
    session.add(event)
    session.flush()
    return event


class DailyAccessRow(NamedTuple):
    """One city-tz day of the access counter (data-model.md §5)."""

    day: date
    unique_tourists: int
    events: int


def _period_filter(*, start_day: date, end_day: date):
    """Inclusive day-range predicate on the precomputed bucket column."""
    return (AccessEvent.day >= start_day, AccessEvent.day <= end_day)


def count_unique_tourist_days(session: Session, *, start_day: date, end_day: date) -> int:
    """Distinct tourist×day pairs in the inclusive range (FR-010).

    Set-based: the distinct (day, tourist_id) pairs are computed by the
    database and just counted — no row loops (FR-020).
    """
    pairs = (
        select(AccessEvent.day, AccessEvent.tourist_id)
        .where(*_period_filter(start_day=start_day, end_day=end_day))
        .distinct()
        .subquery()
    )
    return int(session.execute(select(func.count()).select_from(pairs)).scalar_one())


def count_events(session: Session, *, start_day: date, end_day: date) -> int:
    """Total access events in the inclusive day range (FR-010)."""
    statement = (
        select(func.count())
        .select_from(AccessEvent)
        .where(*_period_filter(start_day=start_day, end_day=end_day))
    )
    return int(session.execute(statement).scalar_one())


def daily_series(session: Session, *, start_day: date, end_day: date) -> list[DailyAccessRow]:
    """Ascending per-day counts (unique tourists + events) in the range.

    One GROUP BY day; only days with at least one event appear
    (edge case: empty window → empty list with zeros).
    """
    unique_tourists = (
        select(
            AccessEvent.day.label("day"),
            func.count(func.distinct(AccessEvent.tourist_id)).label("unique_tourists"),
        )
        .where(*_period_filter(start_day=start_day, end_day=end_day))
        .group_by(AccessEvent.day)
        .subquery()
    )
    totals = (
        select(
            AccessEvent.day.label("day"),
            func.count().label("events"),
        )
        .where(*_period_filter(start_day=start_day, end_day=end_day))
        .group_by(AccessEvent.day)
        .subquery()
    )
    statement = (
        select(
            unique_tourists.c.day,
            unique_tourists.c.unique_tourists,
            func.coalesce(totals.c.events, 0).label("events"),
        )
        .join(totals, totals.c.day == unique_tourists.c.day, isouter=True)
        .order_by(unique_tourists.c.day)
    )
    return [
        DailyAccessRow(day=row.day, unique_tourists=row.unique_tourists, events=row.events)
        for row in session.execute(statement)
    ]
