"""DTOs of the ``tourist_spots`` module (contracts/tourist-spots.md).

All schemas inherit the shared ``ApiModel`` (spec 005 FR-008): JSON keys
are camelCase, Python attributes stay snake_case (PEP 8), input is strict
(``extra="forbid"``, unknown AND snake_case keys → 422).

Wire conventions (research R4/R5/R9/R10): weekdays are day-name strings
(``monday``… ``sunday``; storage is ISO 1..7), times are pure ``HH:MM``
wall-clock strings (city-timezone semantics from ``city_timezone``
configuration), statuses are stored/contracted verbatim
(``open``/``temporarilyClosed``/``permanentlyClosed``). Coordinates are
decimal WGS-84 degrees only (FR-002). The public detail resolves category
labels from the configured catalog (analysis U1) — administrative views
carry the raw keys.
"""

from datetime import datetime, time
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from passanorte_back.core.schemas import ApiModel
from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
    WEEKDAYS,
)


def _parse_clock(value: str) -> time:
    """Parse a strict ``HH:MM`` string into ``datetime.time`` (already
    validated by the pattern + clock validators before reaching here)."""
    return time(hour=int(value[:2]), minute=int(value[3:5]))


def parse_clock(value: str) -> time:
    """Public helper used by the service layer (same guaranteed shape)."""
    return _parse_clock(value)


class SpotStatus(StrEnum):
    """The three operating statuses, stored/contracted verbatim (R9)."""

    OPEN = "open"
    TEMPORARILY_CLOSED = "temporarilyClosed"
    PERMANENTLY_CLOSED = "permanentlyClosed"


SpotName = Annotated[str, Field(min_length=1, max_length=200)]
SpotDescription = Annotated[str, Field(min_length=1, max_length=2000)]
Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
# Per-spot override of the presence radius (feature 011, data-model.md §2):
# meters, positive when present; ``None`` → global settings default.
ToleranceRadius = Annotated[float, Field(gt=0.0)]


class SpotScheduleEntryInput(ApiModel):
    """One schedule entry of a submission (weekday + one open/close interval)."""

    weekday: str
    opens_at: Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]
    closes_at: Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]

    @field_validator("weekday")
    @classmethod
    def _validate_weekday(cls, value: str) -> str:
        if value not in WEEKDAYS:
            raise ValueError(
                f"unknown weekday '{value}': expected one of "
                f"{', '.join(WEEKDAYS)} (opening times precede closing times)"
            )
        return value

    @field_validator("opens_at", "closes_at")
    @classmethod
    def _validate_clock_time(cls, value: str, info) -> str:
        """Strict ``HH:MM`` clock time — ``8:30``, ``25:00``, ``08:70`` and
        ``08:30:00`` are all rejected (pure wall-clock, research R5)."""
        hour, minute = int(value[:2]), int(value[3:5])
        if hour > 23 or minute > 59:
            raise ValueError(
                f"'{info.field_name}' must be a valid HH:MM clock time (received '{value}')"
            )
        return value

    @model_validator(mode="after")
    def _opens_strictly_before_closes(self) -> "SpotScheduleEntryInput":
        """US3-2: opening == closing (or after) is an impossible interval."""
        if _parse_clock(self.opens_at) >= _parse_clock(self.closes_at):
            raise ValueError("opensAt must be strictly before closesAt")
        return self


class CategoryView(ApiModel):
    """One resolved category of the public detail (analysis U1)."""

    key: str
    label: str | None


class SpotScheduleEntryView(ApiModel):
    """Schedule entry as contracted: day name + ``HH:MM`` pure times."""

    weekday: str
    opens_at: str
    closes_at: str


class SpotCreateRequest(ApiModel):
    """POST /tourist-spots request (RF11/RF13/RF14/RF15; contract §1)."""

    name: SpotName
    description: SpotDescription
    latitude: Latitude
    longitude: Longitude
    status: SpotStatus | None = None  # omitted ⇒ "open" at the service (FR-008)
    # Feature 011: omitted/None ⇒ the global settings default (100 m);
    # positive float overrides the presence radius for this spot alone.
    tolerance_radius_m: ToleranceRadius | None = None
    categories: Annotated[list[str], Field(min_length=1)]
    schedule: Annotated[list[SpotScheduleEntryInput], Field(min_length=1)]


class SpotUpdateRequest(ApiModel):
    """PATCH /tourist-spots/{id} request — ALL fields optional (FR-017)."""

    name: SpotName | None = None
    description: SpotDescription | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    status: SpotStatus | None = None
    # Feature 011: absent in patch = unchanged; explicit ``toleranceRadiusM:
    # null`` resets to the global default (feature 011 contract §4).
    tolerance_radius_m: ToleranceRadius | None = None
    categories: Annotated[list[str], Field(min_length=1)] | None = None
    schedule: Annotated[list[SpotScheduleEntryInput], Field(min_length=1)] | None = None


class SpotView(ApiModel):
    """Administrative view of a spot: raw catalog keys (analysis U1)."""

    id: int
    name: str
    description: str
    latitude: float
    longitude: float
    tolerance_radius_m: float | None = None
    status: str
    categories: list[str]
    schedule: list[SpotScheduleEntryView]
    created_at: datetime
    updated_at: datetime


class SpotListResponse(ApiModel):
    """Paginated administrative listing (FR-009/FR-016; contract §2, R11)."""

    items: list[SpotView]
    total: int
    page: int
    page_size: int


class PublicSpotDetailView(ApiModel):
    """Unauthenticated detail for the Passaporte app (RF27; contract §3).

    ``events`` reflects the events domain's public service result; ``mapLink``
    is computed at read time (FR-012) and never stored.
    """

    id: int
    name: str
    description: str
    latitude: float
    longitude: float
    tolerance_radius_m: float | None = None
    status: str
    categories: list[CategoryView]
    schedule: list[SpotScheduleEntryView]
    events: list[dict[str, object]]
    map_link: str
