"""DTOs of the ``visitation`` module (feature 011 — contracts/visitation.md).

All schemas inherit the shared ``ApiModel`` (spec 005): JSON keys are
camelCase, Python attributes stay snake_case, input is strict
(``extra="forbid"`` — unknown AND snake_case keys → 422). Coordinates are
decimal WGS-84 degrees and always finite (FR-013): out-of-range or
non-finite values are rejected at the border, before any distance math.
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from passanorte_back.core.schemas import ApiModel

Latitude = Annotated[
    float,
    Field(ge=-90.0, le=90.0, allow_inf_nan=False),
]
Longitude = Annotated[
    float,
    Field(ge=-180.0, le=180.0, allow_inf_nan=False),
]


class MarkVisitationRequest(ApiModel):
    """POST /visitation/spots/{spotId}/visits body (RF31; contract §1)."""

    latitude: Latitude
    longitude: Longitude


class RouteOutcome(ApiModel):
    """One affected in-progress route of the spec 009 seam (RF34)."""

    route_id: int
    completion_rate: int
    completed: bool


class VisitationMarkedResponse(ApiModel):
    """201 response: the immutable record + whether the seam fired (FR-009)."""

    id: int
    spot_id: int
    visited_at: datetime
    latitude: float
    longitude: float
    first_visit: bool
    route_outcomes: list[RouteOutcome]


class VisitationView(ApiModel):
    """One immutable history row (US4, FR-010)."""

    id: int
    spot_id: int
    visited_at: datetime
    latitude: float
    longitude: float


class VisitationListView(ApiModel):
    """GET /visitation/visitations view: the caller's own ledger."""

    items: list[VisitationView]


class VisitedSpotView(ApiModel):
    """One visited-spots projection row (derived state — data-model.md §1)."""

    spot_id: int
    first_visit_at: datetime
    visit_count: int


class VisitedSpotsView(ApiModel):
    """GET /visitation/visited-spots view: the visited-points projection."""

    items: list[VisitedSpotView]
