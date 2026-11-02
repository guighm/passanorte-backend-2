"""Events service flows (feature 008 US1–US3; research R2/R4/R6/R7/R8).

Routes enforce RBAC (every management operation is admin-only — FR-006);
this layer owns the event data and the cross-module rules. Create/edit
resolve the target tourist spot **exclusively** through this module's
public read seams of ``tourist_spots``: ``get_active_spot_status`` (404 on
unknown/removed) and the public ``STATUS_PERMANENTLY_CLOSED`` constant
(409 on a permanently closed target — research R3). The price persists as
exact integer cents (never float — research R1). Every successful write
emits exactly ONE ``core.audit.record_action`` (RNF19, SC-004). Cascade on
spot removal goes the sanctioned opposite direction:
``tourist_spots.remove_spot`` calls ``delete_spot_events`` (research R4).

``list_public_spot_events`` remains the tourist_spots→events seam promised
by feature 007: the public detail embeds its wire-shaped (camelCase) dicts
verbatim — never an error, ``[]`` for a spot with no events (FR-010).
"""

from datetime import date

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.modules.events import schemas as event_schemas
from passanorte_back.modules.events.repositories.events import (
    Event,
    add_event,
    find_event_by_id,
    list_events,
)
from passanorte_back.modules.events.repositories.events import (
    delete_event as delete_event_row,
)
from passanorte_back.modules.events.repositories.events import (
    delete_spot_events as delete_spot_event_rows,
)
from passanorte_back.modules.events.schemas.events import cents_to_price, price_to_cents
from passanorte_back.modules.tourist_spots.services.tourist_spots import (
    STATUS_PERMANENTLY_CLOSED,
    SpotMissingError,
    get_active_spot_status,
)


class EventMissingError(Exception):
    """Target event does not exist (or was removed) — route → 404."""


class InvalidEventInputError(Exception):
    """Invalid write/listing payload beyond schema shape — route → 422
    (``request_error`` semantic path, 007 precedent)."""


class SpotPermanentlyClosedError(Exception):
    """Target spot is permanently closed — route → 409 ``conflict``
    (research R2); the message names the cause (FR-005)."""


class EventSpotMissingError(Exception):
    """Target spot does not exist (or was removed) — route → 404 (FR-004).

    Owned translation of the tourist_spots ``SpotMissingError`` raised
    through the read seam, so route mapping stays inside this module.
    """


# ---
# Spot validation (one cross-module seam, reused by every write path — R3)
# ---


def _validate_target_spot(session: Session, spot_id: int) -> None:
    """The event's spot must exist and not be permanently closed (FR-004/FR-005)."""
    try:
        status = get_active_spot_status(session, spot_id)
    except SpotMissingError as error:
        raise EventSpotMissingError from error
    if status == STATUS_PERMANENTLY_CLOSED:
        raise SpotPermanentlyClosedError(
            f"tourist spot {spot_id} is permanently closed: events can only "
            "reference spots that are open or temporarily closed"
        )


def _validate_date_range(start_date: date | None, end_date: date | None) -> None:
    """Inclusive range sanity (FR-009): an inverted range is a semantic
    (not shape) error — 422 via the unified ``request_error`` path."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise InvalidEventInputError(
            f"startDate {start_date.isoformat()} is after endDate "
            f"{end_date.isoformat()}: the range bounds must form a non-empty interval"
        )


# ---
# View helpers — the wire shape shared by admin CRUD and the public seam
# ---


def event_to_view(event: Event) -> event_schemas.EventView:
    return event_schemas.EventView.from_internal(
        id=event.id,
        spot_id=event.spot_id,
        occurrence_date=event.occurrence_date,
        description=event.description,
        ticket_price=cents_to_price(event.ticket_price_cents),
    )


def event_to_wire_dict(event: Event) -> dict[str, object]:
    """Wire-shaped (camelCase) dict for the public embedding seam (R8).

    The tourist-spots public detail embeds these dicts verbatim without
    ever importing an events schema type — the module coupling stays on
    this public function.
    """
    view = event_to_view(event)
    return {
        "id": view.id,
        "spotId": view.spot_id,
        "occurrenceDate": view.occurrence_date.isoformat(),
        "description": view.description,
        "ticketPrice": view.ticket_price,
    }


# ---
# Flows (one audit record per successful write — R7)
# ---


def create_event(
    session: Session, *, actor: str, payload: event_schemas.EventCreateRequest
) -> Event:
    """Create an event on an existing, not-permanently-closed spot (RF16)."""
    _validate_target_spot(session, payload.spot_id)
    event = add_event(
        session,
        spot_id=payload.spot_id,
        occurrence_date=payload.occurrence_date,
        description=payload.description,
        ticket_price_cents=price_to_cents(payload.ticket_price),
    )
    record_action(
        actor=actor,
        action="event.create",
        target=f"event:{event.id}",
        result="success",
        detail={
            "spotId": event.spot_id,
            "ticketPrice": str(cents_to_price(event.ticket_price_cents)),
        },
    )
    return event


def update_event(
    session: Session,
    *,
    actor: str,
    event_id: int,
    payload: event_schemas.EventUpdateRequest,
) -> Event:
    """Partial edit (RF17): provided fields change; a provided ``spotId``
    re-validates the NEW target (404/409) with prior state kept on refusal.
    An empty patch is a no-op without an audit record (007 precedent)."""
    event = find_event_by_id(session, event_id)
    if event is None:
        raise EventMissingError("event not found")

    if payload.spot_id is not None and payload.spot_id != event.spot_id:
        _validate_target_spot(session, payload.spot_id)

    changed = False
    if payload.spot_id is not None:
        event.spot_id = payload.spot_id
        changed = True
    if payload.occurrence_date is not None:
        event.occurrence_date = payload.occurrence_date
        changed = True
    if payload.description is not None:
        event.description = payload.description
        changed = True
    if payload.ticket_price is not None:
        event.ticket_price_cents = price_to_cents(payload.ticket_price)
        changed = True

    if changed:
        session.flush()
        session.refresh(event)
        record_action(
            actor=actor,
            action="event.update",
            target=f"event:{event.id}",
            result="success",
            detail={
                "spotId": event.spot_id,
                "ticketPrice": str(cents_to_price(event.ticket_price_cents)),
            },
        )
    return event


def remove_event(session: Session, *, actor: str, event_id: int) -> int:
    """Physical removal (RF17, research R9); returns the former spot id."""
    event = find_event_by_id(session, event_id)
    if event is None:
        raise EventMissingError("event not found")
    spot_id = event.spot_id
    delete_event_row(session, event)
    record_action(
        actor=actor,
        action="event.delete",
        target=f"event:{event_id}",
        result="success",
    )
    return spot_id


def list_events_admin(
    session: Session,
    *,
    spot_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Event]:
    """Administrative combined-filter listing (FR-007/FR-008).

    Unknown ``spotId`` filter → 404 (mirrors creation, spec edge case);
    inverted range → 422 via ``InvalidEventInputError`` (R6).
    """
    _validate_date_range(start_date, end_date)
    if spot_id is not None:
        _validate_target_spot(session, spot_id)
    return list_events(session, spot_id=spot_id, start_date=start_date, end_date=end_date)


# ---
# Public seam (feature 007 contract — the only tourist_spots→events touch)
# ---


def list_public_spot_events(session: Session, spot_id: int) -> list[dict[str, object]]:
    """Events associated to a tourist spot, as exposed publicly (RF27).

    Wire-shaped camelCase dicts (R8), ordered ``(occurrence_date, id)``;
    a spot whose rows were cascade-deleted (spot removal — R4) renders
    ``[]``. Never an error.
    """
    events = list_events(session, spot_id=spot_id)
    return [event_to_wire_dict(event) for event in events]


def delete_spot_events(session: Session, spot_id: int) -> int:
    """Hard delete of a spot's events — the cascade half of research R4.

    Public service function consumed exclusively by
    ``tourist_spots.remove_spot`` in the same transaction; no audit record
    belongs here (the spot domain's ``tourist_spot.delete`` action covers
    the removal — contracts/events.md §5).
    """
    return delete_spot_event_rows(session, spot_id)
