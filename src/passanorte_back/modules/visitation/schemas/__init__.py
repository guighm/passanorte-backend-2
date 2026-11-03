"""HTTP-bound DTOs of the visitation module (all ``ApiModel``, feature 011)."""

from passanorte_back.modules.visitation.schemas.visitations import (
    MarkVisitationRequest,
    RouteOutcome,
    VisitationListView,
    VisitationMarkedResponse,
    VisitationView,
    VisitedSpotsView,
    VisitedSpotView,
)

__all__ = [
    "MarkVisitationRequest",
    "RouteOutcome",
    "VisitedSpotView",
    "VisitedSpotsView",
    "VisitationListView",
    "VisitationMarkedResponse",
    "VisitationView",
]
