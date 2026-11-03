"""Persistence of the ``visitation`` module (feature 011, data-model.md §1).

The ``visitations`` table is the append-only immutable ledger of validated
visits — no update or delete path exists anywhere in this module (FR-006).
``tourist_id``/``tourist_spot_id`` are read-only references into
``tourists``/``tourist_spots`` (constitution rule 4). There is intentionally
NO unique constraint on the (tourist, spot) pair: repeated valid visits
append further rows (clarification Q5 — no throttle); "visited" is derived
from this ledger (clarification Q1).
"""

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base


def _utc_now() -> datetime:
    """Server-side UTC stamp (research R8 — client clocks are untrusted)."""
    return datetime.now(UTC)


class Visitation(Base):
    """One immutable validated visit of a tourist at a tourist spot."""

    __tablename__ = "visitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    tourist_spot_id: Mapped[int] = mapped_column(
        ForeignKey("tourist_spots.id"), index=True
    )  # read-only references (constitution rule 4)
    visited_at: Mapped[datetime] = mapped_column(index=True, default=_utc_now)
    latitude: Mapped[float] = mapped_column()
    longitude: Mapped[float] = mapped_column()


def insert_visit(
    session: Session,
    *,
    tourist_id: int,
    tourist_spot_id: int,
    latitude: float,
    longitude: float,
) -> Visitation:
    """Append one visitation row (timestamp captured server-side, R8)."""
    visitation = Visitation(
        tourist_id=tourist_id,
        tourist_spot_id=tourist_spot_id,
        latitude=latitude,
        longitude=longitude,
    )
    session.add(visitation)
    session.flush()
    return visitation


def exists_for_pair(session: Session, *, tourist_id: int, tourist_spot_id: int) -> bool:
    """Has this tourist already visited this spot (Q1 derivation / FR-007)?"""
    return (
        session.query(Visitation)
        .filter(
            Visitation.tourist_id == tourist_id,
            Visitation.tourist_spot_id == tourist_spot_id,
        )
        .first()
        is not None
    )


def list_for_tourist(session: Session, *, tourist_id: int, limit: int = 200) -> list[Visitation]:
    """The caller's own immutable history, newest first (US4, FR-010)."""
    return list(
        session.query(Visitation)
        .filter(Visitation.tourist_id == tourist_id)
        .order_by(Visitation.visited_at.desc(), Visitation.id.desc())
        .limit(limit)
    )


class VisitedSpotRow:
    """Aggregated projection row (data-model.md §1 — derived, never stored)."""

    __slots__ = ("spot_id", "first_visit_at", "visit_count")

    def __init__(self, spot_id: int, first_visit_at: datetime, visit_count: int) -> None:
        self.spot_id = spot_id
        self.first_visit_at = first_visit_at
        self.visit_count = visit_count


def visited_spots(session: Session, *, tourist_id: int) -> list[VisitedSpotRow]:
    """MIN(visited_at)/COUNT per visited spot, stable spot id order (Q1)."""
    rows = (
        session.query(
            Visitation.tourist_spot_id,
            func.min(Visitation.visited_at),
            func.count(Visitation.id),
        )
        .filter(Visitation.tourist_id == tourist_id)
        .group_by(Visitation.tourist_spot_id)
        .order_by(Visitation.tourist_spot_id)
    )
    return [
        VisitedSpotRow(spot_id=spot_id, first_visit_at=first, visit_count=count)
        for spot_id, first, count in rows
    ]
