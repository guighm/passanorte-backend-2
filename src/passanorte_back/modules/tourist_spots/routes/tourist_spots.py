"""HTTP routes of the ``tourist_spots`` module (contracts/tourist-spots.md).

Mounted on the canonical router (``MODULE_ROUTERS["tourist_spots"]``,
prefix /api/v1/tourist-spots). Tags come exclusively from the central
registry via ``core/routers.py`` — no tag strings here (feature 006,
FR-013). Management operations are admin-only (``require_admin`` — FR-005);
the single-spot detail is public (RF27, added by US5). Failures go through
``HTTPException`` → unified ``ApiError`` (FR-014/FR-015).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_admin,
)
from passanorte_back.modules.tourist_spots import schemas as spot_schemas
from passanorte_back.modules.tourist_spots.services.tourist_spots import (
    InvalidSpotInputError,
    SpotMissingError,
    build_public_detail,
    create_spot,
    get_active_spot,
    list_spots_paged,
    remove_spot,
    spot_to_view,
    update_spot,
)

router = MODULE_ROUTERS["tourist_spots"]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="spot not found")


def _invalid(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("", response_model=spot_schemas.SpotView, status_code=status.HTTP_201_CREATED)
def post_tourist_spot(
    payload: spot_schemas.SpotCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> spot_schemas.SpotView:
    """Create a tourist spot (201; 403 non-admin; 422 invalid — FR-001)."""
    try:
        spot = create_spot(session, actor=admin.username, payload=payload)
    except InvalidSpotInputError as error:
        raise _invalid(error) from error
    return spot_to_view(spot)


@router.get("", response_model=spot_schemas.SpotListResponse)
def get_tourist_spot_list(
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> spot_schemas.SpotListResponse:
    """Bounded administrative listing, optional status filter (FR-009/FR-016)."""
    try:
        spots, total = list_spots_paged(
            session, status=status_filter, page=page, page_size=page_size
        )
    except InvalidSpotInputError as error:
        raise _invalid(error) from error
    return spot_schemas.SpotListResponse.from_internal(
        items=[spot_to_view(spot) for spot in spots],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{spot_id}", response_model=spot_schemas.PublicSpotDetailView)
def get_tourist_spot_public_detail(
    spot_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> spot_schemas.PublicSpotDetailView:
    """Public detail for the Passaporte app (RF27 — no authentication;
    closed spots stay visible; removed/unknown → 404, FR-004)."""
    try:
        spot = get_active_spot(session, spot_id)
    except SpotMissingError as error:
        raise _not_found() from error
    return build_public_detail(session, spot)


@router.patch("/{spot_id}", response_model=spot_schemas.SpotView)
def patch_tourist_spot(
    spot_id: int,
    payload: spot_schemas.SpotUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> spot_schemas.SpotView:
    """Partial edit of any attribute (200; 404 unknown; 422 invalid — FR-003/FR-017)."""
    try:
        spot = update_spot(session, actor=admin.username, spot_id=spot_id, payload=payload)
    except SpotMissingError as error:
        raise _not_found() from error
    except InvalidSpotInputError as error:
        raise _invalid(error) from error
    return spot_to_view(spot)


@router.delete("/{spot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tourist_spot(
    spot_id: int,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> None:
    """Remove a spot (204; idempotent-refused 404 after — FR-004)."""
    try:
        remove_spot(session, actor=admin.username, spot_id=spot_id)
    except SpotMissingError as error:
        raise _not_found() from error
