"""Tourist spot persistence (feature 007 data-model §1; tourist_spots module).

The tables and their data access belong exclusively to the ``tourist_spots``
domain: nobody outside reads or writes these rows directly. The category
catalog is configuration data — rows here persist validated canonical
``category_key`` strings only (clarification Q1: no catalog table, no FK
to one). Removal is logical: ``removed_at`` set hides a spot from every
query (research R6); physical disposal is out of scope.
"""

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import Float, ForeignKey, SmallInteger, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from passanorte_back.core.db import Base

NAME_LENGTH: Final[int] = 200
DESCRIPTION_LENGTH: Final[int] = 2000
CATEGORY_KEY_LENGTH: Final[int] = 50
STATUS_LENGTH: Final[int] = 20

# Stored verbatim = the JSON contract values (research R9).
STATUS_OPEN: Final[str] = "open"
STATUS_TEMPORARILY_CLOSED: Final[str] = "temporarilyClosed"
STATUS_PERMANENTLY_CLOSED: Final[str] = "permanentlyClosed"
VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {STATUS_OPEN, STATUS_TEMPORARILY_CLOSED, STATUS_PERMANENTLY_CLOSED}
)

# JSON contract uses day-name strings; storage uses ISO-8601 integers (R4).
WEEKDAYS: Final[dict[str, int]] = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}
WEEKDAY_NAMES: Final[dict[int, str]] = {number: day for day, number in WEEKDAYS.items()}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TouristSpot(Base):
    """A curated point of interest of the city (feature 007 data-model §1)."""

    __tablename__ = "tourist_spots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_LENGTH))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    # Per-spot override of the presence radius in meters (feature 011). None
    # falls back to the global default (``settings.gps_tolerance_radius_m``).
    tolerance_radius_m: Mapped[float | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(STATUS_LENGTH), default=STATUS_OPEN)
    removed_at: Mapped[datetime | None] = mapped_column(index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)

    categories: Mapped[list["TouristSpotCategory"]] = relationship(
        cascade="all, delete-orphan",
        order_by="TouristSpotCategory.id",  # submitted order preserved
    )
    schedule_entries: Mapped[list["TouristSpotScheduleEntry"]] = relationship(
        cascade="all, delete-orphan",
        order_by="TouristSpotScheduleEntry.weekday",
    )


class TouristSpotCategory(Base):
    """One catalog-key association of a spot (validated at write time)."""

    __tablename__ = "tourist_spot_categories"
    __table_args__ = (
        UniqueConstraint("spot_id", "category_key", name="uq_tourist_spot_categories"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    spot_id: Mapped[int] = mapped_column(
        ForeignKey("tourist_spots.id", ondelete="CASCADE"), index=True
    )
    category_key: Mapped[str] = mapped_column(String(CATEGORY_KEY_LENGTH), index=True)


class TouristSpotScheduleEntry(Base):
    """One weekday-plus-interval entry of a spot's operating schedule."""

    __tablename__ = "tourist_spot_schedule_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    spot_id: Mapped[int] = mapped_column(
        ForeignKey("tourist_spots.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    opens_at: Mapped[datetime] = mapped_column(Time)
    closes_at: Mapped[datetime] = mapped_column(Time)


def add_spot(
    session: Session,
    *,
    name: str,
    description: str,
    latitude: float,
    longitude: float,
    status: str = STATUS_OPEN,
    tolerance_radius_m: float | None = None,
) -> TouristSpot:
    spot = TouristSpot(
        name=name,
        description=description,
        latitude=latitude,
        longitude=longitude,
        status=status,
        tolerance_radius_m=tolerance_radius_m,
    )
    session.add(spot)
    session.flush()
    return spot


def find_active_by_id(session: Session, spot_id: int) -> TouristSpot | None:
    """Active spot only — removed spots are invisible everywhere (R6)."""
    spot = session.get(TouristSpot, spot_id)
    if spot is None or spot.removed_at is not None:
        return None
    return spot


def list_active(session: Session) -> list[TouristSpot]:
    """All active spots, stable id order (data-model §1 — no uniqueness)."""
    return list(
        session.query(TouristSpot).filter(TouristSpot.removed_at.is_(None)).order_by(TouristSpot.id)
    )


def list_active_paged(
    session: Session,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[TouristSpot], int]:
    """Bounded listing page (FR-009/FR-016, research R11): stable id order,
    excludes removed spots, optional exact status filter; (items, total)."""
    query = session.query(TouristSpot).filter(TouristSpot.removed_at.is_(None))
    if status is not None:
        query = query.filter(TouristSpot.status == status)
    total = query.count()
    items = query.order_by(TouristSpot.id).offset((page - 1) * page_size).limit(page_size).all()
    return list(items), total


def _replace_children(
    session: Session, spot: TouristSpot, children: list, new_values: list
) -> None:
    """Delete+insert the association rows of one spot in ONE transaction
    (interests precedent, feature 003)."""
    for child in children:
        session.delete(child)
    session.flush()
    for value in new_values:
        session.add(value)


def replace_categories(session: Session, spot: TouristSpot, keys: list[str]) -> None:
    """Replace the spot's category associations (validated keys only)."""
    _replace_children(
        session,
        spot,
        list(spot.categories),
        [TouristSpotCategory(spot_id=spot.id, category_key=key) for key in keys],
    )


def replace_schedule(session: Session, spot: TouristSpot, entries: list[dict[str, object]]) -> None:
    """Replace the spot's schedule entries from service-validated dicts.

    Each dict: ``weekday`` (ISO 1..7), ``opens_at``/``closes_at``
    (``datetime.time``).
    """
    _replace_children(
        session,
        spot,
        list(spot.schedule_entries),
        [
            TouristSpotScheduleEntry(
                spot_id=spot.id,
                weekday=int(entry["weekday"]),
                opens_at=entry["opens_at"],  # type: ignore[union-attr]
                closes_at=entry["closes_at"],  # type: ignore[union-attr]
            )
            for entry in entries
        ],
    )
