"""HTTP routes of the ``events`` module (contracts/events.md, feature 008).

Mounted on the canonical router (``MODULE_ROUTERS["events"]``, prefix
``/api/v1/events``). Tags come exclusively from the central registry via
``core/routers.py`` — no tag strings here (feature 006, FR-013). Every
management operation is admin-only (``require_admin`` — FR-006); the only
public surface over events is the tourist spot detail embedding (RF27,
consumed through ``modules.events.services.list_public_spot_events``).
Failures go through ``HTTPException`` → unified ``ApiError``: 404
(event or target spot missing), 409 ``conflict`` (target spot permanently
closed — research R2), 422 (shape via the generic validation path,
semantics via ``request_error`` — 007 precedent).
"""

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_admin,
)
from passanorte_back.modules.events import schemas as event_schemas
from passanorte_back.modules.events.services.events import (
    EventMissingError,
    EventSpotMissingError,
    InvalidEventInputError,
    SpotPermanentlyClosedError,
    create_event,
    event_to_view,
    list_events_admin,
    remove_event,
    update_event,
)

router = MODULE_ROUTERS["events"]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="event or tourist spot not found"
    )


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="tourist spot is permanently closed",
    )


def _invalid(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("", response_model=event_schemas.EventView, status_code=status.HTTP_201_CREATED)
def post_event(
    payload: event_schemas.EventCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> event_schemas.EventView:
    """Create an event (201; 403/401 non-admin; 404 unknown spot; 409
    permanently closed spot; 422 invalid — RF16)."""
    try:
        event = create_event(session, actor=admin.username, payload=payload)
    except (EventSpotMissingError, EventMissingError):
        raise _not_found() from None
    except SpotPermanentlyClosedError:
        raise _conflict() from None
    return event_to_view(event)


@router.get("", response_model=event_schemas.EventListResponse)
def get_event_list(
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    spot_id: Annotated[int | None, Query(alias="spotId")] = None,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> event_schemas.EventListResponse:
    """Combined-filter administrative listing, optional spot and inclusive
    date-range bounds (FR-007/FR-008; contract §2)."""
    try:
        events = list_events_admin(
            session, spot_id=spot_id, start_date=start_date, end_date=end_date
        )
    except EventSpotMissingError:
        raise _not_found() from None
    except InvalidEventInputError as error:
        raise _invalid(error) from error
    return event_schemas.EventListResponse.from_internal(
        items=[event_to_view(event) for event in events]
    )


@router.patch("/{event_id}", response_model=event_schemas.EventView)
def patch_event(
    event_id: int,
    payload: event_schemas.EventUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> event_schemas.EventView:
    """Partial edit of any attribute, including re-targeting the spot
    (200; 404 unknown event/spot; 409 permanently closed spot — RF17)."""
    try:
        event = update_event(session, actor=admin.username, event_id=event_id, payload=payload)
    except (EventSpotMissingError, EventMissingError):
        raise _not_found() from None
    except SpotPermanentlyClosedError:
        raise _conflict() from None
    return event_to_view(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_route(
    event_id: int,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> None:
    """Remove an event (204; 404 unknown — RF17)."""
    try:
        remove_event(session, actor=admin.username, event_id=event_id)
    except EventMissingError:
        raise _not_found() from None
