"""HTTP DTOs of the ``dashboard`` module (feature 014 — contracts/dashboard.md).

All schemas inherit the shared ``ApiModel`` (spec 005): JSON keys camelCase
(``spotId``, ``startDate``, ``totalVisitors``…), Python attributes snake_case
(PEP 8), strict input border (``extra="forbid"``, no ``populate_by_name``).
Python construction uses ``ApiModel.from_internal`` (snake_case keywords),
serialized by FastAPI with ``by_alias=True``.
"""

from datetime import date

from pydantic import Field

from passanorte_back.core.schemas import ApiModel


class HeatmapMarker(ApiModel):
    """One heat-map marker (FR-004): coordinates + visit weight (RF06).

    ``spot_id`` is ``None`` on region markers (``groupBy=region``);
    ``name`` is the spot's public name or the region's label.
    """

    spot_id: int | None
    name: str
    latitude: float
    longitude: float
    weight: int = Field(ge=0)


class HeatmapResponse(ApiModel):
    """GET /heatmap — concentration markers in weight-descending order."""

    markers: list[HeatmapMarker]


class AccessDailyCount(ApiModel):
    """One city-tz day of the access counter (FR-010)."""

    date: date
    unique_tourists: int = Field(ge=0)
    access_events: int = Field(ge=0)


class AccessCountsResponse(ApiModel):
    """GET /access-counts — counter over a configurable period (RF07).

    ``unique_tourist_days`` counts distinct tourist×day pairs (the same
    tourist twice on the same day counts once); ``total_access_events``
    counts every recorded request; ``daily`` lists the days WITH events,
    ascending (empty window → zeros + empty list).
    """

    period: str
    unique_tourist_days: int = Field(ge=0)
    total_access_events: int = Field(ge=0)
    daily: list[AccessDailyCount]


class RankingItem(ApiModel):
    """One ranking line (FR-012/FR-014)."""

    position: int = Field(ge=1)
    spot_id: int
    name: str
    visits: int = Field(ge=1)


class SpotRankingResponse(ApiModel):
    """GET /spot-ranking — top N spots of ONE window (Q3)."""

    granularity: str
    reference_date: date | None
    items: list[RankingItem]


class CountryShareItem(ApiModel):
    """One country bucket of the visitor-country distribution (FR-015)."""

    country: str
    tourists: int = Field(ge=0)
    share: float = Field(ge=0.0, le=100.0)


class VisitorCountriesResponse(ApiModel):
    """GET /visitor-countries — proportions over the visitor population."""

    total_visitors: int = Field(ge=0)
    items: list[CountryShareItem]


class InterestShareItem(ApiModel):
    """One category bucket of the visitor-interest distribution (RF10)."""

    interest_key: str
    interest_label: str
    tourists: int = Field(ge=0)
    share: float = Field(ge=0.0, le=100.0)


class VisitorInterestsResponse(ApiModel):
    """GET /visitor-interests — proportion per declared interest.

    A visitor with N interests counts once per interest, so the shares
    are relative to ``total_selections`` and may sum above 100 (US5)."""

    total_visitors: int = Field(ge=0)
    total_selections: int = Field(ge=0)
    items: list[InterestShareItem]
