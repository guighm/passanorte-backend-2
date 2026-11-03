"""Pure geospatial math of the visitation module (feature 011, research R1).

The Haversine great-circle distance with the IUGG mean Earth radius and the
inclusive radius comparison (``distance <= radius`` — spec Edge Cases:
the border is a presence). No geospatial dependency: the exact cases the
spec demands (inside/outside/border/antipodes/zero) are covered by
``tests/unit/test_haversine.py``. The antipode clamp guards the only
numerical trap of the formula (``sqrt(a)`` exceeding 1 by float noise when
both points are exactly antipodal — FR-005 "no false positive").
"""

import math
from typing import Final

EARTH_MEAN_RADIUS_M: Final[float] = 6_371_008.8  # IUGG mean radius (R1)


def haversine_distance_m(
    latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float
) -> float:
    """Great-circle distance in meters between two decimal WGS-84 points."""
    phi_1 = math.radians(latitude_1)
    phi_2 = math.radians(latitude_2)
    delta_phi = math.radians(latitude_2 - latitude_1)
    delta_lambda = math.radians(longitude_2 - longitude_1)
    inner = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Antipode clamp: float noise can push the inner term epsilon above 1.0
    # for exactly antipodal points, sending asin() out of its domain.
    clamped = min(1.0, max(0.0, inner))
    return 2.0 * EARTH_MEAN_RADIUS_M * math.asin(math.sqrt(clamped))


def is_within_radius(distance_m: float, radius_m: float) -> bool:
    """Inclusive border comparison — ``distance <= radius`` is presence."""
    return distance_m <= radius_m


def resolve_tolerance_radius_m(spot, settings) -> float:  # noqa: ANN001
    """Effective radius of a spot (FR-003): the per-spot override when set
    (positive meters), otherwise the global default from settings (R2)."""
    if spot.tolerance_radius_m is not None:
        return spot.tolerance_radius_m
    return settings.gps_tolerance_radius_m
