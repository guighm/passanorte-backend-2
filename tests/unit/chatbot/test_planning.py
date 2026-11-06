"""Unit: itinerary planning criteria (feature 016 — T020 US2, FR-009/010/
011/024, SC-002/SC-003).

Pure-function tests over synthetic candidates on a straight line of
coordinates (0.001° ≈ 111 m): greedy nearest-neighbor ordering must undo
zigzag sequences, suggested times must stay inside operating hours and the
cost total must equal the sum of the event ticket prices.
"""

from datetime import UTC, datetime, time

from passanorte_back.modules.chatbot.services.planning import (
    anchor_selection,
    build_itinerary,
)
from passanorte_back.modules.chatbot.services.retrieval import Candidate

WEDNESDAY = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def _spot(
    ref_id: int, *, lat: float, opens: time | None, closes: time | None, price: int = 0
) -> Candidate:
    return Candidate(
        kind="spot",
        ref_id=ref_id,
        name=f"Spot {ref_id}",
        description="",
        category_keys=[],
        ticket_price_cents=price,
        latitude=lat,
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


def test_greedy_order_undoes_zigzag() -> None:
    """SC-003/FR-011: LLM order A → B → C (11 km, 111 m jump back) is
    re-ordered to A → C → B by nearest-neighbor greedy."""
    far_a = _spot(1, lat=-22.700, opens=None, closes=None)
    far_b = _spot(2, lat=-22.800, opens=None, closes=None)
    near_c = _spot(3, lat=-22.701, opens=None, closes=None)
    plan = build_itinerary(
        [far_a, far_b, near_c],
        generated_at=WEDNESDAY,
        target_day="2026-11-04",
        dwell_minutes=60,
    )
    assert [item.ref_id for item in plan.items] == [1, 3, 2]


def test_suggested_times_stay_inside_operating_hours() -> None:
    """FR-009: a spot already closed by the accumulated dwell time is
    dropped; an spot opening later than 'now' is scheduled at opens_at."""
    now_open = _spot(1, lat=-22.0, opens=time(0, 0), closes=time(23, 0))
    later = _spot(2, lat=-22.1, opens=time(12, 0), closes=time(18, 0))
    closes_soon = _spot(3, lat=-22.2, opens=time(0, 0), closes=time(11, 0))
    plan = build_itinerary(
        [now_open, closes_soon, later],
        generated_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
        target_day="2026-11-04",
        dwell_minutes=60,
    )
    refs = [item.ref_id for item in plan.items]
    assert refs == [1, 2], "item 3 (closed 11:00) must be dropped at 11:00 dwell"
    assert plan.items[0].suggested_at.hour == 10
    assert plan.items[1].suggested_at.hour == 12  # clamped to opening


def test_cost_total_is_sum_of_ticket_prices() -> None:
    """FR-010/SC-002: events count their price, free spots add zero."""
    paid = _event(10, price=2500)
    other = _event(11, price=1500)
    free = _spot(20, lat=-22.0, opens=None, closes=None)
    plan = build_itinerary(
        [free, paid, other],
        generated_at=WEDNESDAY,
        target_day="2026-11-04",
        dwell_minutes=60,
    )
    costs = {item.ref_id: item.ticket_cost_cents for item in plan.items}
    assert costs == {20: 0, 10: 2500, 11: 1500}
    assert plan.total_cost_cents == 4000


def test_unknown_selection_ids_are_anchored_away() -> None:
    """FR-006: ids unknown to the candidate set never enter the plan."""
    real = _spot(5, lat=-22.0, opens=None, closes=None)
    anchored = anchor_selection([5, 999], [], [real])
    assert [candidate.ref_id for candidate in anchored] == [5]
