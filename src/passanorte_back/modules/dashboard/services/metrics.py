"""Metric services of the dashboard module (feature 014).

Time-window math (FR-006/FR-009/FR-012/FR-013; research R4) plus the
read-only metric aggregates (FR-004/FR-012/FR-015/FR-017). Everything is
set-based SQL issued through the dashboard's own read layer, over REAL
recorded rows — no metric is ever estimated (constitution IV). Window
bounds are returned as UTC instants for portable comparisons (research
addendum: SQLite renders aware datetimes as text; PostgreSQL uses
timestamptz) and per-day access metrics map back to city-tz days (RNF06).
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from passanorte_back.core.config import LocationDataError, Settings, get_settings
from passanorte_back.modules.dashboard.repositories.access_events import city_tz
from passanorte_back.modules.dashboard.repositories.read_projections import (
    TOURIST_INTERESTS,
    TOURIST_SPOTS,
    TOURISTS,
    VISITATIONS,
)

_PERIODS: tuple[str, ...] = ("today", "week", "month", "custom")
_GRANULARITIES: tuple[str, ...] = ("day", "month", "year")
_GROUP_BYS: tuple[str, ...] = ("spot", "region")
_DEFAULT_TOP_N = 5
_MAX_TOP_N = 100

logger = logging.getLogger("passanorte.dashboard")


def _utc_now() -> datetime:
    """Injectable clock anchor (unit tests freeze it)."""
    return datetime.now(UTC)


def _settings() -> Settings:
    return get_settings()


def _invalid(message: str = "Dashboard query parameters are invalid.") -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def _zone(key: str):
    from zoneinfo import ZoneInfo

    return ZoneInfo(key)


@dataclass(frozen=True)
class _DayBounds:
    """Inclusive closed window of calendar days."""

    start_day: date
    end_day: date

    def to_datetimes(self, tz) -> tuple[datetime, datetime]:  # noqa: ANN001 — tz is a ZoneInfo
        start = datetime.combine(self.start_day, datetime.min.time(), tzinfo=tz)
        end = (
            datetime.combine(self.end_day, datetime.min.time(), tzinfo=tz)
            + timedelta(days=1)
            - timedelta(microseconds=1)
        )
        # UTC instants: portable comparisons (SQLite text rendering; PG timestamptz).
        return start.astimezone(UTC), end.astimezone(UTC)


def _city_today(settings: Settings, now: datetime) -> date:
    return now.astimezone(_zone(settings.resolved_city_timezone())).date()


def resolve_period_window(
    settings: Settings,
    *,
    period: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Inclusive [start, end] for the counter windows (FR-009).

    ``today``/``week``/``month`` anchor at the city-tz calendar (RNF06)
    and are open periods (end = the current instant); ``custom`` requires
    both dates, inclusive, end ≥ start, closing at the last instant of
    endDate (contracts/dashboard.md §6 — 422 otherwise).
    """
    current = now if now is not None else _utc_now()
    city_tz = _zone(settings.resolved_city_timezone())
    if period is None:
        raise _invalid("The 'period' query parameter is required.")
    if period not in _PERIODS:
        raise _invalid(f"Unknown period '{period}' — expected one of {list(_PERIODS)}.")
    today = current.astimezone(city_tz).date()
    if period == "today":
        start = datetime.combine(today, datetime.min.time(), tzinfo=city_tz)
        return start.astimezone(UTC), current.astimezone(UTC)
    if period == "week":
        week_start = today - timedelta(days=today.weekday())
        start = datetime.combine(week_start, datetime.min.time(), tzinfo=city_tz)
        return start.astimezone(UTC), current.astimezone(UTC)
    if period == "month":
        start = datetime.combine(today.replace(day=1), datetime.min.time(), tzinfo=city_tz)
        return start.astimezone(UTC), current.astimezone(UTC)
    # custom — both dates required, inclusive, ordered (FR-009).
    if start_date is None or end_date is None:
        raise _invalid("The period 'custom' requires 'startDate' and 'endDate'.")
    if end_date < start_date:
        raise _invalid("'endDate' must be greater than or equal to 'startDate'.")
    return _DayBounds(start_date, end_date).to_datetimes(city_tz)


def resolve_distribution_window(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[datetime, datetime] | None:
    """Optional inclusive window of the distributions (FR-006/FR-016).

    ``None`` means all-history aggregation; partial or inverted ranges
    are rejected with 422 (edge case).
    """
    if start_date is None and end_date is None:
        return None
    if start_date is None or end_date is None:
        raise _invalid("The optional 'startDate' and 'endDate' must be provided together.")
    if end_date < start_date:
        raise _invalid("'endDate' must be greater than or equal to 'startDate'.")
    return _DayBounds(start_date, end_date).to_datetimes(
        _zone(_settings().resolved_city_timezone())
    )


def resolve_ranking_window(
    *,
    granularity: str,
    reference_date: date | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """One window per query (clarification Q3): day/month/year of the
    reference date (defaults to the current city-tz date), inclusive."""
    if granularity not in _GRANULARITIES:
        raise _invalid(f"Unknown granularity '{granularity}' — expected 'day', 'month' or 'year'.")
    if reference_date is None:
        reference_date = _city_today(_settings(), _utc_now() if now is None else now)
    if granularity == "day":
        start_day, end_day = reference_date, reference_date
    elif granularity == "month":
        start_day = reference_date.replace(day=1)
        last_day = calendar.monthrange(reference_date.year, reference_date.month)[1]
        end_day = reference_date.replace(day=last_day)
    else:  # year
        start_day = reference_date.replace(month=1, day=1)
        end_day = reference_date.replace(month=12, day=31)
    return _DayBounds(start_day, end_day).to_datetimes(_zone(_settings().resolved_city_timezone()))


def validate_limit(limit: int | None) -> int:
    """Top N of the ranking (FR-013): default 5, inclusive range 1–100."""
    if limit is None:
        return _DEFAULT_TOP_N
    if not 1 <= limit <= _MAX_TOP_N:
        raise _invalid(f"'limit' must be between 1 and {_MAX_TOP_N} (received: {limit}).")
    return limit


def window_to_days(window: tuple[datetime, datetime]) -> tuple[date, date]:
    """City-tz calendar days covered by a UTC instant window (research R3)."""
    tz = city_tz()
    return window[0].astimezone(tz).date(), window[1].astimezone(tz).date()


@dataclass(frozen=True)
class RegionDefinition:
    """One configured heat-map region resolved against registered spots.

    ``latitude``/``longitude`` are the centroid of the KNOWN constituent
    spots (``None`` when the region matches no registered spot);
    ``spot_names`` lists only the spots that resolved (research R5).
    """

    key: str
    label: str
    spot_names: tuple[str, ...]
    latitude: float | None
    longitude: float | None


def resolve_regions(
    settings: Settings, coords_by_name: dict[str, tuple[float, float]]
) -> list[RegionDefinition]:
    """Data-driven region resolution for the heat map (RF06, feature 014).

    Reads the optional ``regions`` block from the location data (RNF06).
    Absent block → the region mode is not available (422, FR-005).
    Unknown spot names are skipped with a structured log; a region whose
    spots are all unknown resolves with centroid ``None``.
    """
    try:
        configured = settings.resolved_regions()
    except LocationDataError as error:
        raise _invalid(str(error)) from error
    if not configured:
        raise _invalid(
            "Region aggregation is unavailable: no 'regions' block in the location data."
        )
    resolved: list[RegionDefinition] = []
    for region in configured:
        known: list[tuple[str, tuple[float, float]]] = []
        for name in region["spots"]:
            coords = coords_by_name.get(name)
            if coords is None:
                logger.warning(
                    "heatmap region '%s' references unknown tourist spot '%s'",
                    region["key"],
                    name,
                )
                continue
            known.append((name, coords))
        latitude = sum(coords[0] for _n, coords in known) / len(known) if known else None
        longitude = sum(coords[1] for _n, coords in known) / len(known) if known else None
        resolved.append(
            RegionDefinition(
                key=region["key"],
                label=region["label"],
                spot_names=tuple(name for name, _coords in known),
                latitude=latitude,
                longitude=longitude,
            )
        )
    return resolved


def _spot_coord_map(session: Session) -> dict[str, tuple[float, float]]:
    """Name → (latitude, longitude) of every registered spot."""
    rows = session.execute(
        select(TOURIST_SPOTS.c.name, TOURIST_SPOTS.c.latitude, TOURIST_SPOTS.c.longitude)
    )
    return {name: (latitude, longitude) for name, latitude, longitude in rows}


def _visit_conditions(window: tuple[datetime, datetime] | None) -> list:
    """Inclusive visited_at predicates for the optional window."""
    conditions = []
    if window is not None:
        conditions.append(VISITATIONS.c.visited_at >= window[0])
        conditions.append(VISITATIONS.c.visited_at <= window[1])
    return conditions


def _spot_counts_by_name(
    session: Session, window: tuple[datetime, datetime] | None
) -> dict[str, int]:
    """Visits-per-spot-name inside the optional window (set-based SQL)."""
    counts = (
        select(
            TOURIST_SPOTS.c.name.label("name"),
            func.count(VISITATIONS.c.id).label("weight"),
        )
        .join(VISITATIONS, VISITATIONS.c.tourist_spot_id == TOURIST_SPOTS.c.id)
        .where(*_visit_conditions(window))
        .group_by(TOURIST_SPOTS.c.id, TOURIST_SPOTS.c.name)
        .subquery()
    )
    return dict(session.execute(select(counts.c.name, counts.c.weight)).fetchall())


def heatmap(
    session: Session,
    *,
    group_by: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    """Heat-map markers (RF06/FR-004): real visit aggregation only.

    ``spot`` mode: one marker per spot with ≥1 visit in the optional
    window (inclusive), descending weight. ``region`` mode: one marker
    per configured region with weight = Σ visits of its known spots and
    centroid coordinates. Removed spots keep counting their history
    (research R7).
    """
    if group_by not in _GROUP_BYS:
        raise _invalid(f"Unknown groupBy '{group_by}' — expected 'spot' or 'region'.")
    window = resolve_distribution_window(start_date=start_date, end_date=end_date)
    markers: list[dict[str, object]] = []

    if group_by == "spot":
        counts = (
            select(
                VISITATIONS.c.tourist_spot_id.label("spot_id"),
                func.count().label("weight"),
            )
            .where(*_visit_conditions(window))
            .group_by(VISITATIONS.c.tourist_spot_id)
            .subquery()
        )
        rows = session.execute(
            select(
                counts.c.spot_id,
                counts.c.weight,
                TOURIST_SPOTS.c.name.label("name"),
                TOURIST_SPOTS.c.latitude.label("latitude"),
                TOURIST_SPOTS.c.longitude.label("longitude"),
            )
            .join(TOURIST_SPOTS, TOURIST_SPOTS.c.id == counts.c.spot_id)
            .order_by(counts.c.weight.desc(), TOURIST_SPOTS.c.id)
        )
        for spot_id, weight, name, latitude, longitude in rows:
            markers.append(
                {
                    "spot_id": spot_id,
                    "name": name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "weight": weight,
                }
            )
        return markers

    # region mode (Q2): per-spot counts merged into configured name groups.
    coords_by_name = _spot_coord_map(session)
    regions = resolve_regions(_settings(), coords_by_name)
    counts_by_name = _spot_counts_by_name(session, window)
    for region in regions:
        weight = sum(counts_by_name.get(name, 0) for name in region.spot_names)
        if weight == 0 or region.latitude is None:
            continue  # concentration markers only (zero-weight/unknown out)
        markers.append(
            {
                "spot_id": None,
                "name": region.label,
                "latitude": region.latitude,
                "longitude": region.longitude,
                "weight": weight,
            }
        )
    return markers


def access_counts(
    session: Session,
    *,
    start_day: date,
    end_day: date,
    period: str | None = None,
) -> dict[str, object]:
    """Access counter (RF07/FR-009/FR-010) over the real ledger.

    ``unique_tourist_days`` = distinct tourist×city-tz-day pairs in the
    inclusive day range; ``total_access_events`` = each recorded request;
    ``daily`` = one row per day with events (ascending) — set-based SQL
    over the indexed bucket column (research R3).
    """
    from passanorte_back.modules.dashboard.repositories.access_events import (
        count_events,
        count_unique_tourist_days,
        daily_series,
    )

    daily = daily_series(session, start_day=start_day, end_day=end_day)
    return {
        "period": period,
        "unique_tourist_days": count_unique_tourist_days(
            session, start_day=start_day, end_day=end_day
        ),
        "total_access_events": count_events(session, start_day=start_day, end_day=end_day),
        "daily": [
            {"date": row.day, "unique_tourists": row.unique_tourists, "access_events": row.events}
            for row in daily
        ],
    }


def spot_ranking(
    session: Session,
    *,
    granularity: str,
    reference_date: date | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Most-visited spot ranking (RF08/FR-012/FR-013/FR-014).

    One window per query (Q3): ``day``/``month``/``year`` of the
    reference date (default: today, city tz). Set-based ORDER BY
    COUNT DESC + stable spot-id tiebreak, LIMIT N; only spots with ≥1
    visit in the window; removed spots keep ranking (research R7).
    """
    window = resolve_ranking_window(granularity=granularity, reference_date=reference_date, now=now)
    top = validate_limit(limit)
    counts = (
        select(
            VISITATIONS.c.tourist_spot_id.label("spot_id"),
            func.count().label("visits"),
        )
        .where(
            VISITATIONS.c.visited_at >= window[0],
            VISITATIONS.c.visited_at <= window[1],
        )
        .group_by(VISITATIONS.c.tourist_spot_id)
        .subquery()
    )
    rows = session.execute(
        select(counts.c.spot_id, counts.c.visits, TOURIST_SPOTS.c.name.label("name"))
        .join(TOURIST_SPOTS, TOURIST_SPOTS.c.id == counts.c.spot_id)
        .order_by(counts.c.visits.desc(), counts.c.spot_id)
        .limit(top)
    )
    return {
        "granularity": granularity,
        "reference_date": reference_date,
        "items": [
            {"position": position, "spot_id": spot_id, "name": name, "visits": visits}
            for position, (spot_id, visits, name) in enumerate(rows, start=1)
        ],
    }


def visitor_countries(
    session: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Visitor-country proportions (RF09/FR-015/FR-016).

    Population: tourists with ≥1 visitation in the optional inclusive
    window. Shares computed IN SQL (ROUND) — set-based, single query
    group, no Python loops (FR-020).
    """
    window = resolve_distribution_window(start_date=start_date, end_date=end_date)
    visitors = (
        select(VISITATIONS.c.tourist_id.label("tourist_id"))
        .where(*_visit_conditions(window))
        .group_by(VISITATIONS.c.tourist_id)
        .subquery()
    )
    joined = (
        select(
            TOURISTS.c.country_of_origin.label("country"),
            visitors.c.tourist_id.label("tourist_id"),
        )
        .join(TOURISTS, TOURISTS.c.id == visitors.c.tourist_id)
        .subquery()
    )
    total = session.execute(select(func.count()).select_from(joined)).scalar_one()
    if total == 0:  # division-by-zero guard (edge case: population vazia)
        return {"total_visitors": 0, "items": []}
    counts = (
        select(
            joined.c.country.label("country"),
            func.count().label("tourists"),
        )
        .group_by(joined.c.country)
        .subquery()
    )
    rows = session.execute(
        select(
            counts.c.country,
            counts.c.tourists,
            func.round(100.0 * counts.c.tourists / total, 1).label("share"),
        ).order_by(counts.c.tourists.desc(), counts.c.country)
    )
    items = [
        {"country": (country or "Não informado"), "tourists": tourists, "share": share}
        for country, tourists, share in rows
    ]
    return {"total_visitors": int(total), "items": items}


def visitor_interests(
    session: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Visitor-interest proportions (RF10/FR-017/FR-018, Q5).

    Population: the SAME visitor set as the country distribution —
    tourists with ≥1 visitation in the optional window. Each declared
    interest of a visitor counts once; shares are computed IN SQL over
    the total selections; unselected categories are absent (US5,
    data-model.md §5).
    """
    window = resolve_distribution_window(start_date=start_date, end_date=end_date)
    visitors = (
        select(VISITATIONS.c.tourist_id.label("tourist_id"))
        .where(*_visit_conditions(window))
        .group_by(VISITATIONS.c.tourist_id)
        .subquery()
    )
    labels = {
        category["key"]: category["label"]
        for category in get_settings().resolved_interest_categories()
    }
    selections = (
        select(
            TOURIST_INTERESTS.c.category_key.label("category_key"),
            visitors.c.tourist_id.label("tourist_id"),
        )
        .join(TOURIST_INTERESTS, TOURIST_INTERESTS.c.tourist_id == visitors.c.tourist_id)
        .subquery()
    )
    total = session.execute(select(func.count()).select_from(selections)).scalar_one()
    if total == 0:  # edge case: no selections → nothing to distribute
        return {"total_visitors": 0, "total_selections": 0, "items": []}
    counts = (
        select(
            selections.c.category_key.label("category_key"),
            func.count().label("tourists"),
        )
        .group_by(selections.c.category_key)
        .subquery()
    )
    rows = session.execute(
        select(
            counts.c.category_key,
            counts.c.tourists,
            func.round(100.0 * counts.c.tourists / total, 1).label("share"),
        ).order_by(counts.c.tourists.desc(), counts.c.category_key)
    )
    items = [
        {
            "interest_key": key,
            "interest_label": labels.get(key, key),
            "tourists": tourists,
            "share": share,
        }
        for key, tourists, share in rows
    ]
    return {
        "total_visitors": int(
            session.execute(select(func.count()).select_from(visitors)).scalar_one()
        ),
        "total_selections": int(total),
        "items": items,
    }
