"""DTOs of the ``gamification`` module (contracts/gamification.md, feature 009).

All schemas inherit the shared ``ApiModel`` (spec 005 FR-008): JSON keys are
camelCase, Python attributes stay snake_case (PEP 8), input is strict
(``extra="forbid"`` — unknown AND snake_case keys → 422).

Wire status enums follow the 007 precedent (``permanentlyClosed``): route
``active``/``archived`` stored via ``removed_at``; enrollment storage
``in_progress``/``completed`` renders as ``inProgress``/``completed``
(data-model §4, F2); code ``unused``/``used`` verbatim.
``completionRate`` is an integer floor percentage 0..100 (research R8).
Names/descriptions are Portuguese user content; all code identifiers are
English (constitution VII).
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from passanorte_back.core.schemas import ApiModel

RouteName = Annotated[str, Field(min_length=1, max_length=200)]
RouteDescription = Annotated[str, Field(min_length=1, max_length=2000)]
SpotId = Annotated[int, Field(ge=1)]
DisplayOrder = Annotated[int, Field(ge=1)]
StockQuantity = Annotated[int, Field(ge=0)]
CompletionRate = Annotated[int, Field(ge=0, le=100)]
RedemptionCodeValue = Annotated[str, Field(min_length=1, max_length=128)]


class RouteSpotItemInput(ApiModel):
    """One spot entry of a route submission (spotId + displayOrder)."""

    spot_id: SpotId
    display_order: DisplayOrder


class RoutePrizeInput(ApiModel):
    """The prize embedded in route creation (born with the route — RF18)."""

    name: Annotated[str, Field(min_length=1, max_length=200)]
    initial_stock: StockQuantity


class RouteCreateRequest(ApiModel):
    """POST /routes request (RF18; contract §1) — every field required.

    ``spots`` cannot be empty (US1-5: empty list → 422).
    """

    name: RouteName
    description: RouteDescription
    spots: Annotated[list[RouteSpotItemInput], Field(min_length=1)]
    prize: RoutePrizeInput


class RouteUpdateRequest(ApiModel):
    """PATCH /routes/{id} request — ALL fields optional (RF19, contract §1).

    A provided ``spots`` is fully re-validated (min 1). The prize is not
    editable here (bound at creation — F1); its stock changes through
    ``PrizeStockUpdateRequest`` (contract §3).
    """

    name: RouteName | None = None
    description: RouteDescription | None = None
    spots: Annotated[list[RouteSpotItemInput], Field(min_length=1)] | None = None


class RouteSpotItemView(ApiModel):
    """One spot entry as contracted on every route read (display order)."""

    spot_id: SpotId
    display_order: DisplayOrder


class RoutePrizeView(ApiModel):
    """Prize summary embedded in route reads (contract §1)."""

    id: int
    name: Annotated[str, Field(min_length=1, max_length=200)]
    stock_quantity: StockQuantity


class TouristRouteView(ApiModel):
    """Route as contracted on create/edit/detail responses (contract §1)."""

    id: int
    name: RouteName
    description: RouteDescription
    spots: list[RouteSpotItemView]
    prize: RoutePrizeView
    status: str  # "active" | "archived" (wire value)


class RouteSummaryView(ApiModel):
    """Listing item (contract §1): route texts + spot count + prize."""

    id: int
    name: RouteName
    description: RouteDescription
    spot_count: DisplayOrder
    prize: RoutePrizeView
    status: str  # "active" | "archived" (wire value)


class RouteListResponse(ApiModel):
    """Route listing body (contract §1) — no pagination this version (YAGNI)."""

    items: list[RouteSummaryView]


class EnrollmentSummaryView(ApiModel):
    """Enrollment summary (contract §2): status, rate, timestamps.

    ``status`` is the wire enum (``inProgress``/``completed`` — data-model
    §4/F2); storage ``in_progress`` maps at the service layer.
    """

    id: int
    route_id: int
    status: str
    completion_rate: CompletionRate
    created_at: datetime
    completed_at: datetime | None


class ProgressSpotView(ApiModel):
    """One route spot of a progress report (contract §2)."""

    spot_id: SpotId
    visited: bool


class BadgeView(ApiModel):
    """Completion badge as contracted (contract §2; RF35)."""

    route_id: int
    granted_at: datetime


class RedemptionCodeView(ApiModel):
    """Redemption code as seen by its owner on the progress payload."""

    code: RedemptionCodeValue
    status: str  # "unused" | "used" (wire value verbatim with storage)


class EnrollmentProgressView(ApiModel):
    """Full progress of an enrollment (contract §2; RF30).

    Badge/code present only when the enrollment is completed (emitted
    once — research R2).
    """

    id: int
    route_id: int
    status: str
    completion_rate: CompletionRate
    created_at: datetime
    completed_at: datetime | None
    spots: list[ProgressSpotView]
    visited_count: int
    total_spots: int
    badge: BadgeView | None
    redemption_code: RedemptionCodeView | None


class EnrollmentListResponse(ApiModel):
    """The tourist's own enrollments (contract §2) — no pagination (YAGNI)."""

    items: list[EnrollmentSummaryView]


class PrizeStockUpdateRequest(ApiModel):
    """PATCH /prizes/{id} request (RF20) — non-negative, ≥ held reservations
    (guard enforced at the service layer)."""

    stock_quantity: StockQuantity


class RedemptionCreateRequest(ApiModel):
    """POST /redemptions request (RF36/Q3; contract §4) — staff only."""

    code: RedemptionCodeValue
    spot_id: SpotId


class RedemptionPrizeView(ApiModel):
    """Prize reference inside a concession record."""

    id: int
    name: str


class RedemptionView(ApiModel):
    """Concession record (contract §4): code consumed, stock unit spent."""

    code: RedemptionCodeValue
    prize: RedemptionPrizeView
    route_id: int
    tourist_id: int
    pickup_spot_id: SpotId
    conceded_by: str
    used_at: datetime
