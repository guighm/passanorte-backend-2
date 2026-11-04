"""Unit: discovery relevance score (feature 013, T007 — spec US1/FR-001..003).

The formula is the single documented one (research.md §R2); every factor is
normalized to [0, 1] and the weighted sum uses the configured weights
(proximity dominant, interests second, events minor — clarification Q1).
Tie-break determinism lives in the sort key, mirrored here.
"""

from datetime import date, timedelta

from passanorte_back.modules.tourist_spots.services.discovery import (
    relevance_score,
)

# Canonical knobs for unit tests (production reads Settings with the same
# defaults): proximity 0.5 / interest 0.35 / event 0.15, max 10 km, window
# 30 days, boost floor 0.25, neutral proximity 0.5.
KNOBS = {
    "w_proximity": 0.5,
    "w_interest": 0.35,
    "w_event": 0.15,
    "max_distance_km": 10.0,
    "event_window_days": 30,
    "event_boost_min": 0.25,
    "neutral_proximity": 0.5,
}
TODAY = date(2026, 11, 3)

INTEREST_SPOT = ["gastronomy", "culture"]
INTEREST_TOURIST = ["gastronomy"]


def test_interest_ratio_is_matches_over_spot_categories() -> None:
    score = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=INTEREST_TOURIST,
        distance_km=None,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    neutral_proximity = 0.5 * KNOBS["w_proximity"]
    expected = neutral_proximity + 0.35 * (1 / 2)
    assert score == expected


def test_full_interest_match_with_position_dominates() -> None:
    # distance 0 km ⇒ proximity factor 1 (dominant 0.5), full match 0.35.
    score = relevance_score(
        spot_categories=["gastronomy"],
        tourist_interests=["gastronomy"],
        distance_km=0.0,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    expected = 0.5 * 1.0 + 0.35 * 1.0 + 0.15 * 0.0
    assert score == expected


def test_proximity_clamps_at_max_distance() -> None:
    at_limit = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=10.0,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    beyond_limit = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=50.0,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    base = 0.35 * 0.0
    assert at_limit == base
    assert beyond_limit == base  # clamped: never negative


def test_no_position_uses_neutral_proximity_constant() -> None:
    none_position = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    # A single request applies ONE proximity regime uniformly: all spots get
    # either the neutral constant (no position) or distance-derived factors.
    assert none_position == 0.5 * KNOBS["w_proximity"]
    far_position = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=10_000.0,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    assert far_position == 0.0  # clamped distances reach zero, never negative


def test_event_boost_grows_as_date_approaches() -> None:
    tomorrow = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=TODAY + timedelta(days=1),
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    next_week = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=TODAY + timedelta(days=7),
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    window_edge = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=TODAY + timedelta(days=30),
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    assert tomorrow > next_week > window_edge
    # At the window's edge the growth has fully receded to the floor.
    floor = KNOBS["w_event"] * KNOBS["event_boost_min"]
    assert window_edge == 0.5 * KNOBS["w_proximity"] + floor


def test_event_floor_beyond_window_and_zero_without_or_past_event() -> None:
    beyond = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=TODAY + timedelta(days=90),
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    floor_score = 0.5 * KNOBS["w_proximity"] + 0.15 * KNOBS["event_boost_min"]
    assert beyond == floor_score

    no_event = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    past = relevance_score(
        spot_categories=INTEREST_SPOT,
        tourist_interests=[],
        distance_km=None,
        upcoming_event_date=TODAY - timedelta(days=1),
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    assert no_event == past == 0.5 * KNOBS["w_proximity"]


def test_score_stays_in_unit_interval() -> None:
    maximal = relevance_score(
        spot_categories=["a"],
        tourist_interests=["a"],
        distance_km=0.0,
        upcoming_event_date=TODAY,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    assert maximal == 1.0


def test_tie_break_key_is_deterministic() -> None:
    from passanorte_back.modules.tourist_spots.services.discovery import tie_break_key

    first = ("Aurora Ponto", 12)
    second = ("aurora ponto", 3)
    # Same name under casefold ⇒ the id decides: 3 ranks before 12.
    assert tie_break_key(1.0, *second) < tie_break_key(1.0, *first)
    assert tie_break_key(1.0, "a", 9) < tie_break_key(1.0, "b", 1)  # name asc
    assert tie_break_key(1.0, "a", 2) < tie_break_key(1.0, "a", 9)  # then id asc
    assert tie_break_key(1.0, "a", 9) < tie_break_key(1.0, "b", 1)  # name asc
    assert tie_break_key(1.0, "b", 1) < tie_break_key(0.9, "a", 99)  # score first


def test_catalog_filter_drops_orphan_keys_so_matches_cannot_survive() -> None:
    """FR-007 edge case (T024): after a location.json catalog shrink (RNF06),
    a spot may still carry its stored category key. The interest factor is
    computed over the configured catalog only, so an orphan key can never
    match — and an all-orphan spot scores interest 0 (denominator is the
    filtered list)."""
    from passanorte_back.modules.tourist_spots.services.discovery import (
        catalog_filtered_categories,
    )

    configured = {"nature", "culture"}  # catalog after the shrink
    assert catalog_filtered_categories(["nature", "vanishing"], configured) == [
        "nature"
    ]  # surviving key keeps the match
    assert catalog_filtered_categories(["vanishing"], configured) == []
    # Empty denominator ⇒ interest 0 ⇒ equals the no-match baseline score.
    orphan_score = relevance_score(
        spot_categories=catalog_filtered_categories(["vanishing"], configured),
        tourist_interests=["vanishing"],  # tourist kept the stored key
        distance_km=None,
        upcoming_event_date=None,
        today=TODAY,
        **KNOBS,  # type: ignore[arg-type]
    )
    assert orphan_score == 0.5 * KNOBS["w_proximity"]  # interest factor 0
