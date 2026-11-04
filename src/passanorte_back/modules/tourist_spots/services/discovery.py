"""Discovery ranking of tourist spots (feature 013 — RF26; T009).

The single documented relevance formula (research.md §R2, spec FR-002 —
re-derivable, deterministic). Three factors normalized to [0, 1]:

- interest  = |spot_categories ∩ tourist_interests| / |spot_categories|
- proximity = clamp(1 - distance_km / max_distance_km, 0, 1);
  no position sent ⇒ the neutral constant for EVERY spot (FR-005)
- event     = floor + (1 - floor) * max(0, 1 - days / window_days) for the
  spot's nearest future event; beyond the window the floor applies; no
  (or past) event ⇒ 0 (FR-001)

score = w_proximity * proximity + w_interest * interest + w_event * event

Ordering: score DESC, then name (case-insensitive) ASC, then id ASC —
never insertion order, current time at sort, or randomness (FR-003).

Cross-module reads go through public service seams only (constitution §3):
tourist interests via ``tourists.services.interests``, future events via
``events.services.list_upcoming_event_dates``. The tourist position is
transient — never persisted (spec FR-014).
"""

import math
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from passanorte_back.core.config import Settings, get_settings
from passanorte_back.modules.events.services.events import list_upcoming_event_dates
from passanorte_back.modules.tourist_spots import schemas as spot_schemas
from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
    TouristSpot,
    list_discovery_candidates,
)
from passanorte_back.modules.tourists.services.interests import list_tourist_interest_keys
from passanorte_back.modules.visitation.services.geolocation import haversine_distance_m


def relevance_score(
    *,
    spot_categories: Sequence[str],
    tourist_interests: Sequence[str],
    distance_km: float | None,
    upcoming_event_date: date | None,
    today: date,
    w_proximity: float,
    w_interest: float,
    w_event: float,
    max_distance_km: float,
    event_window_days: int,
    event_boost_min: float,
    neutral_proximity: float,
) -> float:
    """The documented discovery score (T007 unit contract; research.md §R2)."""
    if len(spot_categories) == 0:
        interest = 0.0
    else:
        own = set(spot_categories)
        interest = len(own.intersection(tourist_interests)) / len(own)

    if distance_km is None:
        proximity = neutral_proximity
    else:
        proximity = min(1.0, max(0.0, 1.0 - distance_km / max_distance_km))

    if upcoming_event_date is None or upcoming_event_date < today:
        event = 0.0
    else:
        days = (upcoming_event_date - today).days
        event = event_boost_min + (1.0 - event_boost_min) * max(0.0, 1.0 - days / event_window_days)

    return w_proximity * proximity + w_interest * interest + w_event * event


def tie_break_key(score: float, name: str, spot_id: int) -> tuple[float, str, int]:
    """Deterministic sort key (FR-003): score DESC → name casefold → id."""
    return (-score, name.casefold(), spot_id)


def catalog_filtered_categories(
    spot_categories: Sequence[str], configured_keys: set[str]
) -> list[str]:
    """Spot categories that still exist in the configured catalog (FR-007
    edge case, T024).

    Persisted association rows survive a ``location.json`` catalog shrink
    (spec 007), so a spot can carry catalog-orphan keys. Discovery matches
    against the CURRENT catalog only: orphan keys are dropped before the
    interest factor — the spot ranks as NON-matching, the denominator uses
    the filtered list, and an all-orphan spot scores interest 0.
    """
    return [key for key in spot_categories if key in configured_keys]


def discover_spots(
    session: Session,
    *,
    tourist_id: int,
    latitude: float | None,
    longitude: float | None,
    page: int,
    page_size: int,
) -> tuple[list[spot_schemas.DiscoveryFeedItem], int, int]:
    """Ranked discovery page: (items, total, total_pages) (spec US1).

    One query per contributing table (research.md §R3): candidates here,
    interests via the tourists seam, nearest future events via the events
    seam. The position is used transiently for the Haversine distance —
    the same metric mandated for presence validation (RNF14).
    """
    from passanorte_back.modules.tourist_spots.services.navigation_links import (
        build_directions_map_link,
    )

    settings: Settings = get_settings()
    today = date.today()
    spots = list_discovery_candidates(session)
    upcoming = dict(list_upcoming_event_dates(session, from_date=today))
    interest_keys = set(list_tourist_interest_keys(session, tourist_id))
    labels = {item["key"]: item["label"] for item in settings.resolved_interest_categories()}
    configured_keys = set(labels)

    scored: list[tuple[float, str, TouristSpot]] = []
    for spot in spots:
        distance_km: float | None = None
        if latitude is not None and longitude is not None:
            distance_km = (
                haversine_distance_m(latitude, longitude, spot.latitude, spot.longitude) / 1000.0
            )
        score = relevance_score(
            spot_categories=catalog_filtered_categories(
                [category.category_key for category in spot.categories],
                configured_keys,
            ),
            tourist_interests=interest_keys,
            distance_km=distance_km,
            upcoming_event_date=upcoming.get(spot.id),
            today=today,
            w_proximity=settings.discovery_w_proximity,
            w_interest=settings.discovery_w_interest,
            w_event=settings.discovery_w_event,
            max_distance_km=settings.discovery_max_distance_km,
            event_window_days=settings.discovery_event_window_days,
            event_boost_min=settings.discovery_event_boost_min,
            neutral_proximity=settings.discovery_neutral_proximity,
        )
        scored.append((score, spot.name, spot.id))

    scored.sort(key=lambda entry: (entry[0] * -1.0, entry[1].casefold(), entry[2]))

    total = len(scored)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    start = (page - 1) * page_size
    page_entries = scored[start : start + page_size]
    by_id = {spot.id: spot for spot in spots}

    items = [
        spot_schemas.DiscoveryFeedItem.from_internal(
            id=by_id[spot_id].id,
            name=by_id[spot_id].name,
            description=by_id[spot_id].description,
            latitude=by_id[spot_id].latitude,
            longitude=by_id[spot_id].longitude,
            status=by_id[spot_id].status,
            categories=[
                spot_schemas.CategoryView(
                    key=category.category_key, label=labels.get(category.category_key)
                )
                for category in by_id[spot_id].categories
            ],
            relevance_score=round(score, 6),
            upcoming_event_date=upcoming.get(spot_id),
            map_link=build_directions_map_link(
                by_id[spot_id].latitude,
                by_id[spot_id].longitude,
                origin=None,
                provider=settings.discovery_map_provider,
            ),
        )
        for score, _name, spot_id in page_entries
    ]
    return items, total, total_pages
