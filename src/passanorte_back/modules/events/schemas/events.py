"""DTOs of the ``events`` module (contracts/events.md, feature 008).

All schemas inherit the shared ``ApiModel`` (spec 005 FR-008): JSON keys
are camelCase, Python attributes stay snake_case (PEP 8), input is strict
(``extra="forbid"`` — unknown AND snake_case keys → 422).

Money convention (research R1): the wire field ``ticketPrice`` is a
``Decimal`` with exactly 2 decimal places, ≥ 0, magnitude capped by the
storage contract (integer cents, max_digits=12); zero means a free event.
The service layer converts through ``price_to_cents``/``cents_to_price`` —
never a float on the storage side. ``occurrenceDate`` is a pure ISO
calendar date with no time-of-day and no timezone semantics (research
R11). Descriptions are Portuguese user content (1..2000 chars), while all
code identifiers and docstrings are English (constitution VII).
"""

from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from typing import Annotated

from pydantic import Field

from passanorte_back.core.schemas import ApiModel

TicketSpotId = Annotated[int, Field(ge=1)]
OccurrenceDate = date  # pure ISO calendar date (YYYY-MM-DD on the wire)
EventDescription = Annotated[str, Field(min_length=1, max_length=2000)]
TicketPrice = Annotated[Decimal, Field(ge=0, decimal_places=2, max_digits=12)]


class EventCreateRequest(ApiModel):
    """POST /events request (RF16; contract §1) — every field required."""

    spot_id: TicketSpotId
    occurrence_date: OccurrenceDate
    description: EventDescription
    ticket_price: TicketPrice


class EventUpdateRequest(ApiModel):
    """PATCH /events/{id} request — ALL fields optional (RF17, contract §3).

    Omitted fields stay unchanged; an empty patch is a no-op (200, no
    audit — 007 ``update_spot`` precedent). A provided ``spotId`` is
    re-validated against the new target spot by the service (404/409).
    """

    spot_id: TicketSpotId | None = None
    occurrence_date: OccurrenceDate | None = None
    description: EventDescription | None = None
    ticket_price: TicketPrice | None = None


class EventView(ApiModel):
    """Event as contracted on every read path (create/edit responses,
    listings, public embedding — SC-005).

    ``ticketPrice`` is a JSON number here (Pydantic v2 serializes
    ``Decimal`` as a string — the exactness lives in the storage layer:
    cents in, ``cents_to_price`` out, two-decimal values only, so every
    number round-trips bit-identically in JSON).
    """

    id: int
    spot_id: TicketSpotId
    occurrence_date: OccurrenceDate
    description: EventDescription
    ticket_price: Annotated[float, Field(ge=0)]


class EventListResponse(ApiModel):
    """Administrative filtered listing body (FR-007/FR-008; contract §2).

    No pagination this version (spec 008 assumption): every matching row
    is returned, ordered ``(occurrenceDate, id)`` ascending.
    """

    items: list[EventView]


def price_to_cents(price: Decimal) -> int:
    """Exact wire ``Decimal`` → integer cents (research R1).

    ``Decimal`` arithmetic only — never a float in between. Values with
    more than 2 decimal places or negatives do not pass the schema border,
    but the helper independently defends the storage invariant.
    """
    scaled = price.scaleb(2).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    if scaled != price.scaleb(2):
        raise ValueError(
            f"ticket price {price} has more than two decimal places: "
            "the exact monetary amount must be expressible in integer cents"
        )
    if price < 0:
        raise ValueError("ticket price must be non-negative")
    if scaled > 999999999999:
        raise ValueError("ticket price exceeds the contract magnitude cap")
    return int(scaled)


def cents_to_price(cents: int) -> Decimal:
    """Integer cents → exact wire ``Decimal`` with 2 places (research R1)."""
    if cents < 0:
        raise ValueError("ticket price must be non-negative")
    if cents > 999999999999:
        raise ValueError("ticket price exceeds the contract magnitude cap")
    return Decimal(cents).scaleb(-2).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
