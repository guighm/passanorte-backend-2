"""HTTP routes of the ``visitation`` module (feature 011 — contracts/visitation.md).

Mounted on the canonical router (``MODULE_ROUTERS["visitation"]``, prefix
``/api/v1/visitation``). The tag comes exclusively from the central
registry via ``core/routers.py`` — no tag strings here (feature 006).
Every endpoint is tourist-exclusive (``require_tourist``; failures mirror
the ``events``/``gamification`` handler style). All failures go through
``HTTPException`` → unified ``ApiError`` (401/403/404/409/422).

Docs use camelCase ``{spotId}`` in URL templates (spec 009 precedent):
code path variables stay snake_case; the OpenAPI border renders the HTTP
path as contracted.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_tourist,
)
from passanorte_back.modules.tourist_spots.services.tourist_spots import SpotMissingError
from passanorte_back.modules.visitation import schemas as visitation_schemas
from passanorte_back.modules.visitation.services.visitations import (
    OutsideToleranceError,
    TouristMissingError,
    list_visitations,
    list_visited_spots,
    mark_visitation,
)

router = MODULE_ROUTERS["visitation"]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _outside(error: OutsideToleranceError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post(
    "/spots/{spot_id}/visits",
    response_model=visitation_schemas.VisitationMarkedResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_visitation(
    spot_id: int,
    payload: visitation_schemas.MarkVisitationRequest,
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> visitation_schemas.VisitationMarkedResponse:
    """Mark the visitation at a spot with GPS presence validation
    (RF31/RF32/RF33; 201 — 404 unknown/inactive spot; 409 outside radius)."""
    try:
        return mark_visitation(
            session,
            user=tourist,
            spot_id=spot_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
    except (SpotMissingError, TouristMissingError) as error:
        raise _not_found(str(error)) from error
    except OutsideToleranceError as error:
        raise _outside(error) from error


@router.get(
    "/visitations",
    response_model=visitation_schemas.VisitationListView,
)
def get_visitations(
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> visitation_schemas.VisitationListView:
    """The caller's own immutable visitation history, newest first (US4)."""
    return list_visitations(session, user=tourist)


@router.get(
    "/visited-spots",
    response_model=visitation_schemas.VisitedSpotsView,
)
def get_visited_spots(
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> visitation_schemas.VisitedSpotsView:
    """The caller's visited-points projection (US4 — derived, Q1)."""
    return list_visited_spots(session, user=tourist)
