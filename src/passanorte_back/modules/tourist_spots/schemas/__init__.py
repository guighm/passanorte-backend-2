"""HTTP-bound DTOs of the tourist_spots module (all ``ApiModel``)."""

from passanorte_back.modules.tourist_spots.schemas.tourist_spots import (
    CategoryView,
    DiscoveryFeedItem,
    DiscoveryFeedResponse,
    NavigationLinksRequest,
    NavigationLinksView,
    NavigationOrigin,
    PublicSpotDetailView,
    SpotCreateRequest,
    SpotListResponse,
    SpotScheduleEntryInput,
    SpotScheduleEntryView,
    SpotStatus,
    SpotUpdateRequest,
    SpotView,
    parse_clock,
)

__all__ = [
    "CategoryView",
    "DiscoveryFeedItem",
    "DiscoveryFeedResponse",
    "NavigationLinksRequest",
    "NavigationLinksView",
    "NavigationOrigin",
    "PublicSpotDetailView",
    "SpotCreateRequest",
    "SpotListResponse",
    "SpotScheduleEntryInput",
    "SpotScheduleEntryView",
    "SpotStatus",
    "SpotUpdateRequest",
    "SpotView",
    "parse_clock",
]
