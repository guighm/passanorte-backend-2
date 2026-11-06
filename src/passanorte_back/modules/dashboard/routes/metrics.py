"""HTTP routes of the ``dashboard`` module (feature 014 — contracts/dashboard.md).

Mounted on the canonical router (``MODULE_ROUTERS["dashboard"]``, prefix
``/api/v1/dashboard``); the tag comes exclusively from the central
registry via ``core/routers.py`` — no tag strings here (spec 006, FR-002).
Every endpoint is admin-only (``auth.services.require_admin`` — RF03:
401 anonymous, 403 employee/tourist). Failures raise ``HTTPException``
→ unified ``ApiError`` (spec 005).
"""

from datetime import date
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from passanorte_back.core.config import get_settings
from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_admin,
)
from passanorte_back.modules.dashboard import schemas as dashboard_schemas
from passanorte_back.modules.dashboard.services import metrics as metrics_service

router = MODULE_ROUTERS["dashboard"]

_SessionDep = Annotated[Session, Depends(get_session)]
_AdminDep = Annotated[AuthenticatedUser, Depends(require_admin)]


@router.get("/access-counts", response_model=dashboard_schemas.AccessCountsResponse)
def get_access_counts(
    session: _SessionDep,
    _admin: _AdminDep,
    period: Annotated[
        str,
        Query(
            description="Period of the counter: today / week / month or "
            "'custom' with both dates (inclusive).",
            pattern="^(today|week|month|custom)$",
        ),
    ] = "today",
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> dashboard_schemas.AccessCountsResponse:
    """Access counter of the Passaporte app (RF07/FR-009/FR-010): distinct
    tourist×day pairs, total recorded events and the daily series for the
    requested period — all derived from the real access ledger."""
    window = metrics_service.resolve_period_window(
        get_settings(),
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    start_day, end_day = metrics_service.window_to_days(window)
    counts = metrics_service.access_counts(
        session, start_day=start_day, end_day=end_day, period=period
    )
    return dashboard_schemas.AccessCountsResponse.from_internal(
        period=counts["period"],
        unique_tourist_days=counts["unique_tourist_days"],
        total_access_events=counts["total_access_events"],
        daily=[
            dashboard_schemas.AccessDailyCount.from_internal(**item) for item in counts["daily"]
        ],
    )


@router.get("/visitor-countries", response_model=dashboard_schemas.VisitorCountriesResponse)
def get_visitor_countries(
    session: _SessionDep,
    _admin: _AdminDep,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> dashboard_schemas.VisitorCountriesResponse:
    """Visitor-country distribution (RF09): proportions of the tourists
    who visited points, segmented by the registered country of origin —
    over real profile + visitation data only (FR-015/FR-016)."""
    distribution = metrics_service.visitor_countries(
        session, start_date=start_date, end_date=end_date
    )
    return dashboard_schemas.VisitorCountriesResponse.from_internal(
        total_visitors=distribution["total_visitors"],
        items=[
            dashboard_schemas.CountryShareItem.from_internal(**item)
            for item in distribution["items"]
        ],
    )


@router.get("/visitor-interests", response_model=dashboard_schemas.VisitorInterestsResponse)
def get_visitor_interests(
    session: _SessionDep,
    _admin: _AdminDep,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> dashboard_schemas.VisitorInterestsResponse:
    """Visitor-interest distribution (RF10): proportions of the same
    visitor population segmented by the interests declared in their
    profiles (Q5) — real interest selections only (FR-017/FR-018)."""
    distribution = metrics_service.visitor_interests(
        session, start_date=start_date, end_date=end_date
    )
    return dashboard_schemas.VisitorInterestsResponse.from_internal(
        total_visitors=distribution["total_visitors"],
        total_selections=distribution["total_selections"],
        items=[
            dashboard_schemas.InterestShareItem.from_internal(**item)
            for item in distribution["items"]
        ],
    )


@router.get("/spot-ranking", response_model=dashboard_schemas.SpotRankingResponse)
def get_spot_ranking(
    session: _SessionDep,
    _admin: _AdminDep,
    granularity: Annotated[
        str,
        Query(
            description="Ranking window: a single day, month or year (one window "
            "per query — clarification Q3).",
            pattern="^(day|month|year)$",
        ),
    ] = "day",
    reference_date: Annotated[date | None, Query(alias="referenceDate")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> dashboard_schemas.SpotRankingResponse:
    """Most-visited spot ranking (RF08): top N spots (default 5, max 100)
    ordered by real visits within the requested window; only visited
    spots appear (FR-014)."""
    ranking = metrics_service.spot_ranking(
        session,
        granularity=granularity,
        reference_date=reference_date,
        limit=limit,
    )
    return dashboard_schemas.SpotRankingResponse.from_internal(
        granularity=ranking["granularity"],
        reference_date=ranking["reference_date"],
        items=[dashboard_schemas.RankingItem.from_internal(**item) for item in ranking["items"]],
    )


@router.get("/heatmap", response_model=dashboard_schemas.HeatmapResponse)
def get_heatmap(
    session: _SessionDep,
    _admin: _AdminDep,
    group_by: Annotated[
        str,
        Query(
            alias="groupBy",
            description="Aggregation mode: by registered spot or by configured "
            "region (requires the data block — FR-005).",
            pattern="^(spot|region)$",
        ),
    ] = "spot",
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> dashboard_schemas.HeatmapResponse:
    """Heat map of visit concentrations (RF06): markers (latitude,
    longitude, weight) aggregated by spot or region — real visit counts
    within the optional inclusive window (FR-004/FR-006/FR-005)."""
    markers = metrics_service.heatmap(
        session, group_by=group_by, start_date=start_date, end_date=end_date
    )
    return dashboard_schemas.HeatmapResponse.from_internal(
        markers=[dashboard_schemas.HeatmapMarker.from_internal(**marker) for marker in markers]
    )  # spot markers + centroid region markers (RF06)
