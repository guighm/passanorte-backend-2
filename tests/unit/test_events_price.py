"""Unit tests: exact-money DTOs of the events module (feature 008 T003).

Pure schema-level tests — no app machinery. Money rules: the ticket price
round-trips exactly between the wire ``Decimal`` (2 places) and the stored
integer cents (research R1); negatives and >2 decimals are rejected at the
border; the strict ``ApiModel`` border rejects unknown AND snake_case keys
(spec 005); ``occurrenceDate`` is a pure ISO calendar date (R11).
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from passanorte_back.modules.events.schemas.events import (
    EventCreateRequest,
    cents_to_price,
    price_to_cents,
)

MINIMAL_BODY = {
    "spotId": 1,
    "occurrenceDate": "2026-12-08",
    "description": "Festival de luzes no mirante.",
    "ticketPrice": 0,
}


# ---
# Money conversion helpers (research R1)
# ---


@pytest.mark.parametrize(
    ("price", "cents"),
    [
        (Decimal("0.00"), 0),  # zero = free event
        (Decimal("0.01"), 1),
        (Decimal("15.50"), 1550),
        (Decimal("987654.32"), 98765432),
        (Decimal("9999999999.99"), 999999999999),  # contract max magnitude
    ],
)
def test_price_cents_round_trip_exact(price: Decimal, cents: int) -> None:
    assert price_to_cents(price) == cents
    assert cents_to_price(cents) == price


def test_zero_price_is_free_and_stable() -> None:
    assert cents_to_price(0) == Decimal("0.00")
    assert price_to_cents(Decimal("0")) == 0


def test_price_to_cents_rejects_more_than_two_places() -> None:
    with pytest.raises(ValueError, match="two decimal places"):
        price_to_cents(Decimal("15.505"))


def test_price_to_cents_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        price_to_cents(Decimal("-0.01"))


# ---
# DTO shapes: strict border + field rules (contracts §1)
# ---


def test_create_request_accepts_camel_case_wire_body() -> None:
    request = EventCreateRequest.model_validate(MINIMAL_BODY)
    assert request.spot_id == 1
    assert request.occurrence_date.year == 2026
    assert request.ticket_price == Decimal("0")


def test_create_request_rejects_unknown_keys() -> None:
    body = {**MINIMAL_BODY, "surprise": 1}
    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate(body)


def test_create_request_rejects_snake_case_keys() -> None:
    body = {
        "spot_id": 1,
        "occurrenceDate": "2026-12-08",
        "description": "x",
        "ticketPrice": 0,
    }
    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate(body)


@pytest.mark.parametrize("malformed", ["08-12-2026", "2026-13-01", "20261208", "2026-12"])
def test_occurrence_date_must_be_iso_calendar_date(malformed: str) -> None:
    body = {**MINIMAL_BODY, "occurrenceDate": malformed}
    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate(body)


def test_description_bounds_1_to_2000() -> None:
    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate({**MINIMAL_BODY, "description": ""})
    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate({**MINIMAL_BODY, "description": "x" * 2001})
    ok_min = EventCreateRequest.model_validate({**MINIMAL_BODY, "description": "x"})
    ok_max = EventCreateRequest.model_validate({**MINIMAL_BODY, "description": "x" * 2000})
    assert ok_min.description == "x"
    assert ok_max.description == "x" * 2000


@pytest.mark.parametrize("bad_price", [-0.01, "15.505", 10000000000.00, "abc", None])
def test_ticket_price_rejects_invalid_values(bad_price) -> None:  # noqa: ANN001
    body = {**MINIMAL_BODY, "ticketPrice": bad_price}
    with pytest.raises(ValidationError):
        EventCreateRequest.model_validate(body)


def test_patch_request_all_keys_optional() -> None:
    from passanorte_back.modules.events.schemas.events import EventUpdateRequest

    empty = EventUpdateRequest()
    assert empty.spot_id is None
    assert empty.occurrence_date is None
    assert empty.description is None
    assert empty.ticket_price is None
    partial = EventUpdateRequest.model_validate({"ticketPrice": 15.5})
    assert partial.ticket_price == Decimal("15.50") or partial.ticket_price == Decimal("15.5")
