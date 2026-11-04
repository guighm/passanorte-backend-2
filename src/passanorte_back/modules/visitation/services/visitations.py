"""Service flows of the ``visitation`` module (feature 011 — spec RF31–RF34).

``mark_visitation`` is the one write flow: validate the tourist and the
active spot through the owner modules' public interfaces, resolve the
effective tolerance radius, check presence with the Haversine distance
(rejected attempts are logged and never persisted — SC-007), append the
immutable record, and — ONLY for the tourist's first visitation of that
spot (FR-009) — call the public spec 009 seam
(``gamification.services.register_spot_visit``) so in-progress routes
update in the SAME transaction (research R4). Reads (US4) are pure
projections of the ledger (clarification Q1 — no status table).
"""

import logging

from sqlalchemy.orm import Session

from passanorte_back.core.config import get_settings
from passanorte_back.modules.auth.services.security import AuthenticatedUser
from passanorte_back.modules.gamification.services import register_spot_visit
from passanorte_back.modules.gamification.services.gamification import (
    TouristMissingError as SeamTouristMissingError,
)
from passanorte_back.modules.tourist_spots.services.tourist_spots import (
    get_active_spot,
)
from passanorte_back.modules.tourists.services.tourists import get_tourist_account
from passanorte_back.modules.visitation import schemas as visitation_schemas
from passanorte_back.modules.visitation.repositories import (
    visitations as visitation_repositories,
)
from passanorte_back.modules.visitation.services import geolocation

logger = logging.getLogger(__name__)


class TouristMissingError(Exception):
    """The authenticated account has no tourist record (R7) — route → 404."""


class OutsideToleranceError(Exception):
    """Valid coordinates beyond the effective radius (FR-004) — route → 409."""


def mark_visitation(
    session: Session,
    *,
    user: AuthenticatedUser,
    spot_id: int,
    latitude: float,
    longitude: float,
) -> visitation_schemas.VisitationMarkedResponse:
    """Validate presence, append the immutable record, fire the seam once.

    Tourist exclusive by construction (route ``require_tourist``). Same
    session = same transaction: a failure in the progress update rolls the
    whole mark back (edge-case consistency policy of the spec, R4).
    """
    if get_tourist_account(session, user.account_id) is None:
        raise TouristMissingError("tourist record not found for the authenticated account")
    spot = get_active_spot(session, spot_id)  # missing/inactive → SpotMissingError (404)

    settings = get_settings()
    radius_m = geolocation.resolve_tolerance_radius_m(spot, settings)
    distance_m = geolocation.haversine_distance_m(
        latitude, longitude, spot.latitude, spot.longitude
    )
    if not geolocation.is_within_radius(distance_m, radius_m):
        # Rejected attempts leave a structured trace, never a row (SC-007/Q6).
        logger.warning(
            "outside_tolerance_radius",
            extra={
                "tourist_id": user.account_id,
                "tourist_spot_id": spot.id,
                "distance_m": round(distance_m, 3),
                "effective_radius_m": radius_m,
            },
        )
        raise OutsideToleranceError(
            f"position is outside the spot radius: {distance_m:.1f} m > {radius_m:.1f} m"
        )

    first_visit = not visitation_repositories.exists_for_pair(
        session, tourist_id=user.account_id, tourist_spot_id=spot.id
    )
    visitation = visitation_repositories.insert_visit(
        session,
        tourist_id=user.account_id,
        tourist_spot_id=spot.id,
        latitude=latitude,
        longitude=longitude,
    )

    route_outcomes: list[visitation_schemas.RouteOutcome] = []
    if first_visit:
        outcomes = _update_routes(session, tourist_id=user.account_id, tourist_spot_id=spot.id)
        route_outcomes = [
            visitation_schemas.RouteOutcome.from_internal(
                route_id=outcome.route_id,
                completion_rate=outcome.completion_rate,
                completed=outcome.completed,
            )
            for outcome in outcomes
        ]

    return visitation_schemas.VisitationMarkedResponse.from_internal(
        id=visitation.id,
        spot_id=visitation.tourist_spot_id,
        visited_at=visitation.visited_at,
        latitude=visitation.latitude,
        longitude=visitation.longitude,
        first_visit=first_visit,
        route_outcomes=route_outcomes,
    )


def _update_routes(session: Session, *, tourist_id: int, tourist_spot_id: int) -> list:
    """RF34 through the owner module's public seam (research R3) — the ONLY
    gamification touchpoint of this module; never its tables."""
    try:
        return register_spot_visit(session, tourist_id=tourist_id, tourist_spot_id=tourist_spot_id)
    except SeamTouristMissingError as error:  # pre-validated above; belt-and-braces
        raise TouristMissingError("tourist record not found") from error


def list_visitations(
    session: Session, *, user: AuthenticatedUser
) -> visitation_schemas.VisitationListView:
    """The caller's own immutable history, newest first (US4, FR-010)."""
    rows = visitation_repositories.list_for_tourist(session, tourist_id=user.account_id)
    return visitation_schemas.VisitationListView(
        items=[
            visitation_schemas.VisitationView.from_internal(
                id=row.id,
                spot_id=row.tourist_spot_id,
                visited_at=row.visited_at,
                latitude=row.latitude,
                longitude=row.longitude,
            )
            for row in rows
        ]
    )


def list_visited_spots(
    session: Session, *, user: AuthenticatedUser
) -> visitation_schemas.VisitedSpotsView:
    """The visited-points projection derived from the ledger (Q1, FR-010)."""
    rows = visitation_repositories.visited_spots(session, tourist_id=user.account_id)
    return visitation_schemas.VisitedSpotsView(
        items=[
            visitation_schemas.VisitedSpotView.from_internal(
                spot_id=row.spot_id,
                first_visit_at=row.first_visit_at,
                visit_count=row.visit_count,
            )
            for row in rows
        ]
    )
