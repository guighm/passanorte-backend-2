"""Unit: the Haversine formula + tolerance-radius resolution (feature 011, FR-005/R1).

Exact cases demanded by the spec acceptance criteria: zero distance, inside,
outside, exact border (inclusive), antipodes (no false positive from angle
wrapping) — plus the radius resolution rule (per-spot override wins; None
falls back to the global settings default).
"""

import math

import pytest

from passanorte_back.modules.visitation.services.geolocation import (
    EARTH_MEAN_RADIUS_M,
    haversine_distance_m,
    is_within_radius,
    resolve_tolerance_radius_m,
)

MUNHOZ = (-22.7271, -45.0366)  # test spot anchor (decimal WGS-84)


def test_zero_distance_is_exactly_accepted_as_within_any_positive_radius() -> None:
    coordinates_identical = haversine_distance_m(*MUNHOZ, *MUNHOZ)
    assert coordinates_identical == pytest.approx(0.0, abs=1e-9)
    assert is_within_radius(coordinates_identical, 25.0)


def test_inside_radius_one_degree_latitude_anchor() -> None:
    d = haversine_distance_m(*MUNHOZ, -21.7271, -45.0366)  # 1° of latitude north
    assert d == pytest.approx(111_194.9, rel=1e-4)  # 2πR/360 meters (research R1)
    assert not is_within_radius(d, 100.0)
    assert is_within_radius(d, 150_000.0)


def test_border_is_inclusive_distance_equal_radius() -> None:
    # d = 100 m north of the anchor: exact by construction (Δφ = radius/R rad);
    # sub-micron float noise of the round-trip is tolerated by the approx.
    exactly_radius_deg = (100.0 / EARTH_MEAN_RADIUS_M) * 360.0 / (2 * math.pi)
    border = haversine_distance_m(*MUNHOZ, MUNHOZ[0] + exactly_radius_deg, MUNHOZ[1])
    assert border == pytest.approx(100.0, abs=1e-3)
    # Inclusive semantics (spec Edge Cases): a measured distance never
    # exceeds itself — with a margin of one millimeter on each side.
    assert is_within_radius(border, border)  # distance == radius accepted
    assert not is_within_radius(border + 1e-3, border)  # 1 mm beyond: rejected
    assert not is_within_radius(border, border - 1e-3)  # radius 1 mm shorter: rejected


def test_outside_radius_clearly_distant_position() -> None:
    d = haversine_distance_m(*MUNHOZ, -22.7266, -45.0366)  # ~55 m north
    assert d == pytest.approx(55.6, rel=1e-2)
    assert is_within_radius(d, 100.0)
    far = haversine_distance_m(*MUNHOZ, -22.6820, -45.0366)  # ~5 km north
    assert far > 5_000.0
    assert not is_within_radius(far, 100.0)


def test_antipodes_rejected_without_false_positive() -> None:
    exact_antipode = haversine_distance_m(0.0, 0.0, 0.0, 180.0)
    assert exact_antipode == pytest.approx(
        math.pi * EARTH_MEAN_RADIUS_M, rel=1e-6
    )  # πR — half the great circle (research R1)
    assert not is_within_radius(exact_antipode, 100.0)
    # Dateline crossing: (-179.5°, 179.5°) is 1° of longitude apart through
    # the wrap — the formula must add, not subtract (≈ 111.195 km at the
    # equator), never a false positive from the longitude wrap.
    across_dateline = haversine_distance_m(0.0, 179.5, 0.0, -179.5)
    assert across_dateline == pytest.approx(111_194.9, rel=1e-4)
    assert not is_within_radius(across_dateline, 100.0)


def test_resolve_radius_spot_override_wins_then_settings_default() -> None:
    class _Settings:
        gps_tolerance_radius_m = 100.0

    class _Spot:
        def __init__(self, radius: float | None) -> None:
            self.tolerance_radius_m = radius

    assert resolve_tolerance_radius_m(_Spot(None), _Settings()) == 100.0
    assert resolve_tolerance_radius_m(_Spot(25.0), _Settings()) == 25.0
