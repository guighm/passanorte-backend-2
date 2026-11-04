"""HTTP routes of the ``gamification`` module (feature 009; contracts/gamification.md).

Mounted on the canonical router (``MODULE_ROUTERS["gamification"]``, prefix
``/api/v1/gamification``). Tags come exclusively from the central registry
via ``core/routers.py`` — no tag strings here (feature 006). Management is
admin-only (``require_admin``, FR-013); tourist self-service is
tourist-only (``require_tourist``); concession is staff-gated (US4).
Feature 012 (RF21) hardens the redemption contract: the 201 response
carries the prize's post-deduction stock, the two 409 causes answer with
distinct canonical messages (already-used vs no-stock) and the failure
paths never alter state. Failures go through
``HTTPException`` → unified ``ApiError`` (401/403/404/409/422), mirroring
the ``events`` module handler style.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    get_current_user,
    require_admin,
    require_staff,
    require_tourist,
)
from passanorte_back.modules.gamification import schemas as gamification_schemas
from passanorte_back.modules.gamification.services.gamification import (
    CodeAlreadyUsedError,
    CodeMissingError,
    EnrollmentConflictError,
    EnrollmentMissingError,
    InvalidRouteInputError,
    PrizeMissingError,
    PrizeStockInsufficientError,
    RouteMissingError,
    TouristMissingError,
    TouristSpotMissingError,
    adjust_prize_stock,
    archive_route_flow,
    concede_prize,
    create_route,
    enroll_tourist,
    enrollment_to_summary_view,
    find_prize_by_id,
    get_enrollment_progress_view,
    get_route_available,
    get_route_for_admin,
    list_routes_active,
    list_routes_admin,
    list_tourist_enrollments,
    route_to_summary_view,
    route_to_view,
    update_route,
)

router = MODULE_ROUTERS["gamification"]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tourist route not found")


def _invalid(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


# ---
# US1: route management (RF18/RF19) — admin only, one audit record per write
# ---


@router.post(
    "/routes",
    response_model=gamification_schemas.TouristRouteView,
    status_code=status.HTTP_201_CREATED,
)
def post_route(
    payload: gamification_schemas.RouteCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> gamification_schemas.TouristRouteView:
    """Create a route with its embedded prize (201; 403/401 non-admin;
    404 unknown/removed spot; 422 invalid — RF18)."""
    try:
        route = create_route(session, actor=admin.username, payload=payload)
    except (RouteMissingError, TouristSpotMissingError):
        raise _not_found() from None
    except InvalidRouteInputError as error:
        raise _invalid(error) from error
    return route_to_view(route)


@router.patch("/routes/{route_id}", response_model=gamification_schemas.TouristRouteView)
def patch_route(
    route_id: int,
    payload: gamification_schemas.RouteUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> gamification_schemas.TouristRouteView:
    """Partial edit (200; 404 unknown/archived route or bad spot; 422
    invalid — RF19)."""
    try:
        route = update_route(session, actor=admin.username, route_id=route_id, payload=payload)
    except (RouteMissingError, TouristSpotMissingError):
        raise _not_found() from None
    except InvalidRouteInputError as error:
        raise _invalid(error) from error
    return route_to_view(route)


@router.delete("/routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: int,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> None:
    """Archive a route with history preserved (204; 404 unknown — RF19,
    Removal Decision)."""
    try:
        archive_route_flow(session, actor=admin.username, route_id=route_id)
    except RouteMissingError:
        raise _not_found() from None


@router.get("/routes", response_model=gamification_schemas.RouteListResponse)
def get_route_list(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    include_archived: Annotated[bool, Query(alias="includeArchived")] = False,
) -> gamification_schemas.RouteListResponse:
    """Listing (contract §1): active routes for any authenticated caller;
    `includeArchived=true` is admin-only (Removal Decision)."""
    if include_archived and user.account_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient permissions"
        )
    routes = (
        list_routes_admin(session, include_archived=True)
        if include_archived
        else list_routes_active(session)
    )
    return gamification_schemas.RouteListResponse.from_internal(
        items=[route_to_summary_view(route) for route in routes]
    )


@router.get("/routes/{route_id}", response_model=gamification_schemas.TouristRouteView)
def get_route_detail(
    route_id: int,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> gamification_schemas.TouristRouteView:
    """Detail (contract §1): admin reads any state; non-admins read active
    routes only (404 on archived — Removal Decision)."""
    try:
        route = (
            get_route_for_admin(session, route_id)
            if user.account_type == "admin"
            else get_route_available(session, route_id)
        )
    except RouteMissingError:
        raise _not_found() from None
    return route_to_view(route)


# ---
# US2: enrollment + progress (RF29/RF30) — tourist-only, self-scoped (FR-013)
# ---


def _tourist_id(user: AuthenticatedUser) -> int:
    return user.account_id


@router.post(
    "/routes/{route_id}/enrollments",
    response_model=gamification_schemas.EnrollmentSummaryView,
    status_code=status.HTTP_201_CREATED,
)
def post_enrollment(
    route_id: int,
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> gamification_schemas.EnrollmentSummaryView:
    """Enroll the caller in the route (201; 409 duplicate enrollment;
    404 unknown/archived route or unknown tourist; 403 non-tourist — RF29)."""
    try:
        enrollment = enroll_tourist(session, tourist_id=_tourist_id(tourist), route_id=route_id)
    except (RouteMissingError, TouristMissingError):
        raise _not_found() from None
    except EnrollmentConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="tourist is already enrolled in this route",
        ) from None
    return enrollment_to_summary_view(session, enrollment)


@router.get("/enrollments", response_model=gamification_schemas.EnrollmentListResponse)
def get_enrollment_list(
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> gamification_schemas.EnrollmentListResponse:
    """The caller's own enrollments, newest first (contract §2; FR-013)."""
    return gamification_schemas.EnrollmentListResponse.from_internal(
        items=list_tourist_enrollments(session, _tourist_id(tourist))
    )


@router.get(
    "/enrollments/{enrollment_id}",
    response_model=gamification_schemas.EnrollmentProgressView,
)
def get_enrollment_progress(
    enrollment_id: int,
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> gamification_schemas.EnrollmentProgressView:
    """Full progress of the caller's enrollment (200; 404 unknown or
    foreign — indistinguishable, FR-013): spots visited/pending, rate and
    — when completed — the badge and the single-use code (RF30/RF35/RF36)."""
    try:
        view = get_enrollment_progress_view(session, _tourist_id(tourist), enrollment_id)
    except EnrollmentMissingError:
        raise _not_found() from None
    return view


# ---
# US4: prize stock (RF20) + staff concession (RF36/Q3)
# ---


@router.patch("/prizes/{prize_id}", response_model=gamification_schemas.RoutePrizeView)
def patch_prize_stock(
    prize_id: int,
    payload: gamification_schemas.PrizeStockUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> gamification_schemas.RoutePrizeView:
    """Adjust a prize's stock (200; 404 unknown; 422 negative or below
    committed reservations — RF20)."""
    try:
        prize = adjust_prize_stock(
            session, actor=admin.username, prize_id=prize_id, stock_quantity=payload.stock_quantity
        )
    except PrizeMissingError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prize not found"
        ) from None
    except InvalidRouteInputError as error:
        raise _invalid(error) from error
    return gamification_schemas.RoutePrizeView.from_internal(
        id=prize.id, name=prize.name, stock_quantity=prize.stock_quantity
    )


@router.post(
    "/redemptions",
    response_model=gamification_schemas.RedemptionView,
    status_code=status.HTTP_201_CREATED,
)
def post_redemption(
    payload: gamification_schemas.RedemptionCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    staff: Annotated[AuthenticatedUser, Depends(require_staff)],
) -> gamification_schemas.RedemptionView:
    """Register the prize concession against a code (201; 409 already used
    or insufficient stock — the code stays valid; 404 unknown code/spot —
    RF36/Q3)."""
    try:
        concession = concede_prize(
            session, actor=staff.username, code=payload.code, spot_id=payload.spot_id
        )
    except (CodeMissingError, TouristSpotMissingError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="redemption code or tourist spot not found",
        ) from None
    except CodeAlreadyUsedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="redemption code has already been used",
        ) from None
    except PrizeStockInsufficientError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no stock available for this route's prize",
        ) from None
    prize = find_prize_by_id(session, concession.prize_id)
    assert prize is not None  # FK guarantees the prize exists
    return gamification_schemas.RedemptionView.from_internal(
        code=concession.code,
        prize=gamification_schemas.RedemptionPrizeView.from_internal(
            id=prize.id,
            name=prize.name,
            stock_quantity=prize.stock_quantity,  # post-deduction (RF21/FR-004)
        ),
        route_id=concession.route_id,
        tourist_id=concession.tourist_id,
        pickup_spot_id=concession.pickup_spot_id,
        conceded_by=concession.conceded_by,
        used_at=concession.used_at,
    )
