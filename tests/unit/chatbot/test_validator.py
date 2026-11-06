"""Unit: FR-021 constraint validator (feature 016 — T021 US2, SC-002).

The validator is the last line of defense: every itinerary the module
presents must reference only existing candidates, respect operating hours,
keep events on the target day and sum the ticket costs honestly.
"""

from dataclasses import replace
from datetime import UTC, datetime, time

from passanorte_back.modules.chatbot.services.planning import build_itinerary
from passanorte_back.modules.chatbot.services.retrieval import Candidate
from passanorte_back.modules.chatbot.services.validator import validate_plan

WEDNESDAY = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
TARGET = "2026-11-04"


def _with_suggested_at(plan, item_index: int, suggested_at: datetime):
    """A frozen-plan rebuild with one item's suggested time drifted."""
    items = [
        replace(item, suggested_at=suggested_at) if index == item_index else item
        for index, item in enumerate(plan.items)
    ]
    return replace(plan, items=items)


def _spot(ref_id: int, *, opens: time | None, closes: time | None) -> Candidate:
    return Candidate(
        kind="spot",
        ref_id=ref_id,
        name=f"Spot {ref_id}",
        description="",
        category_keys=[],
        ticket_price_cents=0,
        latitude=-22.0,
        longitude=-45.0,
        opens_at=opens,
        closes_at=closes,
    )


def _event(ref_id: int, *, price: int) -> Candidate:
    return Candidate(
        kind="event",
        ref_id=ref_id,
        name=f"Event {ref_id}",
        description="",
        category_keys=[],
        ticket_price_cents=price,
        latitude=-22.0,
        longitude=-45.0,
    )


def test_valid_plan_passes() -> None:
    spot = _spot(1, opens=time(0, 0), closes=time(23, 0))
    plan = build_itinerary([spot], generated_at=WEDNESDAY, target_day=TARGET, dwell_minutes=60)
    result = validate_plan(plan, [spot], target_day=TARGET)
    assert result.ok, [issue.reason for issue in result.issues]


def test_unanchorable_item_is_rejected() -> None:
    """FR-006: the invented item must be flagged and excluded."""
    real = _spot(1, opens=time(0, 0), closes=time(23, 0))
    invented = _spot(999, opens=time(0, 0), closes=time(23, 0))
    plan = build_itinerary(
        [real, invented], generated_at=WEDNESDAY, target_day=TARGET, dwell_minutes=60
    )
    result = validate_plan(plan, [real], target_day=TARGET)
    assert not result.ok
    assert any(issue.ref_id == 999 for issue in result.issues)
    assert [item.ref_id for item in result.valid_items] == [1]


def test_closed_at_suggested_time_is_rejected() -> None:
    """FR-009: suggested 11:30 with an 11:00 closing → invalid item."""
    spot = _spot(1, opens=time(0, 0), closes=time(11, 0))
    plan = build_itinerary([spot], generated_at=WEDNESDAY, target_day=TARGET, dwell_minutes=60)
    drifted = _with_suggested_at(plan, 0, datetime(2026, 11, 4, 11, 30, tzinfo=UTC))
    result = validate_plan(drifted, [spot], target_day=TARGET)
    assert not result.ok
    assert any("closed" in issue.reason for issue in result.issues)


def test_event_off_target_day_is_rejected() -> None:
    """FR-024: an event scheduled to a different day fails the constraint."""
    event = _event(10, price=2500)
    plan = build_itinerary(
        [event], generated_at=WEDNESDAY, target_day="2026-11-04", dwell_minutes=60
    )
    drifted = _with_suggested_at(plan, 0, datetime(2026, 11, 9, 10, 0, tzinfo=UTC))
    result = validate_plan(drifted, [event], target_day=TARGET)
    assert not result.ok
    assert any("target day" in issue.reason for issue in result.issues)


def test_cost_sum_is_enforced() -> None:
    """FR-010: the item price drifted from the registered price → invalid."""
    event = _event(10, price=2500)
    plan = build_itinerary([event], generated_at=WEDNESDAY, target_day=TARGET, dwell_minutes=60)
    forged = replace(
        plan,
        items=[replace(plan.items[0], ticket_cost_cents=999999)],
    )
    result = validate_plan(forged, [event], target_day=TARGET)
    assert not result.ok
    assert any("cost" in issue.reason for issue in result.issues)
