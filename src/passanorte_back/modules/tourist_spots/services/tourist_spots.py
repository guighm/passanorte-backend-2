"""Tourist spot management flows (feature 007 US1–US5; research R7–R14).

Routes enforce RBAC (every write/listing is admin-only — FR-005); this
layer owns the spot data. Write flows emit exactly ONE
``core.audit.record_action`` each (RNF19, SC-004). Removal is logical
(``removed_at`` — research R6); removed spots vanish from every operation
but their audit trail stays.

Validation split (R13): SHAPE rules live in the schemas (coordinates,
``HH:MM`` parse, ``opensAt < closesAt``, weekday names, ≥1 entry,
≥1 category); CONFIG-DATA and cross-entry rules live here — category keys
against the configured catalog and same-day overlap of intervals (US2/US3;
422 via the unified error path).
"""

from datetime import time
from urllib.parse import quote

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.modules.tourist_spots import schemas as spot_schemas

# Module-level re-export: part of the public interface for cross-module
# consumers (feature 008 research R3) — never imported from repositories.
from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (  # noqa: F401
    STATUS_OPEN,
    STATUS_PERMANENTLY_CLOSED,
    VALID_STATUSES,
    WEEKDAY_NAMES,
    WEEKDAYS,
    TouristSpot,
    add_spot,
    find_active_by_id,
    list_active_paged,
    replace_categories,
    replace_schedule,
)


class SpotMissingError(Exception):
    """Target spot does not exist (or was removed) — route → 404 (FR-004)."""


class InvalidSpotInputError(Exception):
    """Invalid write payload beyond schema shape — route → 422 (FR-00x)."""


class OverlappingScheduleError(InvalidSpotInputError):
    """Overlapping intervals for the same weekday in one submission (US3-5)."""


# ---
# View helpers (R4/R9/R10 — contract representations computed at read time)
# ---


def _schedule_views(spot: TouristSpot) -> list[spot_schemas.SpotScheduleEntryView]:
    return [
        spot_schemas.SpotScheduleEntryView.from_internal(
            weekday=WEEKDAY_NAMES[entry.weekday],
            opens_at=entry.opens_at.strftime("%H:%M"),
            closes_at=entry.closes_at.strftime("%H:%M"),
        )
        for entry in spot.schedule_entries
    ]


def spot_to_view(spot: TouristSpot) -> spot_schemas.SpotView:
    return spot_schemas.SpotView.from_internal(
        id=spot.id,
        name=spot.name,
        description=spot.description,
        latitude=spot.latitude,
        longitude=spot.longitude,
        status=spot.status,
        categories=[category.category_key for category in spot.categories],
        schedule=_schedule_views(spot),
        created_at=spot.created_at,
        updated_at=spot.updated_at,
    )


def build_map_link(latitude: float, longitude: float) -> str:
    """Google Maps universal link computed from decimal coordinates (R10).

    Read-time computation only — never stored (FR-012).
    """
    return (
        "https://www.google.com/maps/search/?api=1&query="
        f"{_format_degree(latitude)},{_format_degree(longitude)}"
    )


def _format_degree(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return quote(text)


# ---
# Shared write validations (US2/US3 — config data + cross-entry rules)
# ---


def _validate_category_keys(keys: list[str]) -> None:
    """Catalog validation on every write of the categories (FR-006, R13)."""
    from passanorte_back.core.config import get_settings

    if len(keys) != len(set(keys)):
        raise InvalidSpotInputError("duplicated category keys in the submission")
    configured = {item["key"] for item in get_settings().resolved_interest_categories()}
    for key in keys:
        if key not in configured:
            raise InvalidSpotInputError(
                f"invalid category: '{key}' is not in the configured catalog"
            )


def _validate_schedule_entries(
    entries: list[spot_schemas.SpotScheduleEntryInput],
) -> None:
    """Same-day overlap rejection (pairwise, US3-4/US3-5; R13)."""
    by_day: dict[int, list[tuple[time, time, str, str]]] = {}
    for entry in entries:
        intervals = by_day.setdefault(WEEKDAYS[entry.weekday], [])
        intervals.append(
            (
                spot_schemas.parse_clock(entry.opens_at),
                spot_schemas.parse_clock(entry.closes_at),
                entry.opens_at,
                entry.closes_at,
            )
        )
    for _weekday, intervals in by_day.items():
        intervals.sort(key=lambda item: (item[0], item[1]))
        for (
            _opens,
            closes,
            _opens_text,
            closes_text,
        ), (next_opens, _, next_opens_text, _) in zip(intervals[:-1], intervals[1:], strict=True):
            if next_opens < closes:  # strict overlap (touching end==open is valid)
                raise OverlappingScheduleError(
                    f"overlapping schedule intervals for weekday "
                    f"'{WEEKDAY_NAMES[int(_weekday)]}': {_opens_text}-"
                    f"{closes_text} overlaps {next_opens_text}"
                )


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise InvalidSpotInputError(f"unknown operating status: '{status}'")


# ---
# Flows (one audit record per successful write — R12)
# ---


def create_spot(
    session: Session, *, actor: str, payload: spot_schemas.SpotCreateRequest
) -> TouristSpot:
    """Create a spot; omitted status defaults to "open" (FR-008)."""
    status = STATUS_OPEN if payload.status is None else payload.status.value
    _validate_status(status)
    _validate_category_keys(payload.categories)
    _validate_schedule_entries(payload.schedule)

    spot = add_spot(
        session,
        name=payload.name,
        description=payload.description,
        latitude=payload.latitude,
        longitude=payload.longitude,
        status=status,
    )
    replace_categories(
        session,
        spot,
        list(dict.fromkeys(payload.categories)),  # order-preserving keys
    )
    replace_schedule(
        session,
        spot,
        [
            {
                "weekday": WEEKDAYS[entry.weekday],
                "opens_at": spot_schemas.parse_clock(entry.opens_at),
                "closes_at": spot_schemas.parse_clock(entry.closes_at),
            }
            for entry in payload.schedule
        ],
    )
    session.flush()  # pending state written; refresh reloads real state
    session.refresh(spot)  # relationship collections reloaded for the view
    record_action(
        actor=actor,
        action="tourist_spot.create",
        target=f"tourist-spot:{spot.id}",
        result="success",
        detail={"status": spot.status, "categories": len(payload.categories)},
    )
    return spot


def update_spot(
    session: Session,
    *,
    actor: str,
    spot_id: int,
    payload: spot_schemas.SpotUpdateRequest,
) -> TouristSpot:
    """Partial edit (FR-017): only provided fields change; provided
    categories/schedule lists are fully re-validated."""
    spot = get_active_spot(session, spot_id)

    changed = False
    if payload.categories is not None:
        _validate_category_keys(payload.categories)
        replace_categories(session, spot, list(dict.fromkeys(payload.categories)))
        changed = True
    if payload.schedule is not None:
        _validate_schedule_entries(payload.schedule)
        replace_schedule(
            session,
            spot,
            [
                {
                    "weekday": WEEKDAYS[entry.weekday],
                    "opens_at": spot_schemas.parse_clock(entry.opens_at),
                    "closes_at": spot_schemas.parse_clock(entry.closes_at),
                }
                for entry in payload.schedule
            ],
        )
        changed = True
    if payload.status is not None:
        _validate_status(payload.status.value)
        spot.status = payload.status.value
        changed = True
    if payload.name is not None:
        spot.name = payload.name
        changed = True
    if payload.description is not None:
        spot.description = payload.description
        changed = True
    if payload.latitude is not None:
        spot.latitude = payload.latitude
        changed = True
    if payload.longitude is not None:
        spot.longitude = payload.longitude
        changed = True

    if changed:
        session.flush()  # pending state written; refresh reloads real state
        session.refresh(spot)  # relationship collections reloaded for the view
        record_action(
            actor=actor,
            action="tourist_spot.update",
            target=f"tourist-spot:{spot.id}",
            result="success",
            detail={"status": spot.status, "categories": len(spot.categories)},
        )
    return spot


def remove_spot(session: Session, *, actor: str, spot_id: int) -> None:
    """Soft delete (R6): hides the spot everywhere; terminal in this milestone.

    The events cascade (feature 008 clarification 2 of session
    2026-11-02, research R4): events cease to exist together with the
    spot — the write crosses domains exclusively through the events
    module's public service function in the SAME transaction, so no
    orphaned event ever survives a listing (FR-014).
    """
    spot = get_active_spot(session, spot_id)
    from datetime import UTC, datetime

    from passanorte_back.modules.events.services import events as events_service

    events_service.delete_spot_events(session, spot.id)
    spot.removed_at = datetime.now(UTC)
    record_action(
        actor=actor,
        action="tourist_spot.delete",
        target=f"tourist-spot:{spot.id}",
        result="success",
        detail={"status": spot.status},
    )


def get_active_spot(session: Session, spot_id: int) -> TouristSpot:
    spot = find_active_by_id(session, spot_id)
    if spot is None:
        raise SpotMissingError("tourist spot not found")
    return spot


def get_active_spot_status(session: Session, spot_id: int) -> str:
    """Operating status of an active spot, for cross-module consumers
    (feature 008 research R3).

    The sanctioned read seam of this module: other domains never touch
    ``TouristSpot`` or its repositories — they call this function and
    compare against the public ``STATUS_PERMANENTLY_CLOSED`` constant.
    Raises ``SpotMissingError`` for unknown/removed spots (route → 404).
    """
    return get_active_spot(session, spot_id).status


def list_spots_paged(
    session: Session,
    *,
    status: str | None = None,
    page: int,
    page_size: int,
) -> tuple[list[TouristSpot], int]:
    """Paginated administrative listing (FR-009/FR-016, R11)."""
    if status is not None:
        _validate_status(status)
    return list_active_paged(session, status=status, page=page, page_size=page_size)


def build_public_detail(session: Session, spot: TouristSpot) -> spot_schemas.PublicSpotDetailView:
    """Public detail for the Passaporte app (RF27; contract §3, U1/R8)."""
    from passanorte_back.core.config import get_settings
    from passanorte_back.modules.events.services import list_public_spot_events

    labels = {item["key"]: item["label"] for item in get_settings().resolved_interest_categories()}
    categories = [
        spot_schemas.CategoryView(
            key=category.category_key, label=labels.get(category.category_key)
        )
        for category in spot.categories
    ]
    return spot_schemas.PublicSpotDetailView.from_internal(
        id=spot.id,
        name=spot.name,
        description=spot.description,
        latitude=spot.latitude,
        longitude=spot.longitude,
        status=spot.status,
        categories=categories,
        schedule=_schedule_views(spot),
        events=list_public_spot_events(session, spot.id),
        map_link=build_map_link(spot.latitude, spot.longitude),
    )
