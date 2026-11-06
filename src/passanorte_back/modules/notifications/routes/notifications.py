"""Delivery routes of the ``notifications`` module (feature 015).

Same conventions as ``routes/subscriptions.py``: canonical router + central
tag (no tag strings here), tourist-exclusive, unified ``ApiError`` failures.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_tourist,
)
from passanorte_back.modules.notifications import schemas as notification_schemas
from passanorte_back.modules.notifications.services import delivery as delivery_service

router = MODULE_ROUTERS["notifications"]

_SessionDep = Annotated[Session, Depends(get_session)]
_TouristDep = Annotated[AuthenticatedUser, Depends(require_tourist)]


def _view(
    data: dict[str, object],
) -> notification_schemas.NotificationView:
    return notification_schemas.NotificationView.from_internal(**data)


@router.get("", response_model=notification_schemas.NotificationsResponse)
def get_notifications(
    session: _SessionDep,
    tourist: _TouristDep,
    only_unread: Annotated[bool, Query(alias="onlyUnread")] = True,
) -> notification_schemas.NotificationsResponse:
    """Polling delivery (RF37): most-recent list — unread by default; the
    payload always carries the tourist's complete unread total (Q4)."""
    payload = delivery_service.list_notifications(
        session, tourist_id=tourist.account_id, only_unread=only_unread
    )
    return notification_schemas.NotificationsResponse.from_internal(
        unread_count=payload["unread_count"],
        items=[_view(item) for item in payload["items"]],  # type: ignore[arg-type]
    )


@router.get("/unread-count", response_model=notification_schemas.UnreadCountResponse)
def get_unread_count(
    session: _SessionDep,
    tourist: _TouristDep,
) -> notification_schemas.UnreadCountResponse:
    """Cheap polling probe (Q5/FR-013a): total unread of the tourist."""
    total = delivery_service.unread_count(session, tourist_id=tourist.account_id)
    return notification_schemas.UnreadCountResponse.from_internal(unread_count=total)


@router.post(
    "/{notification_id}/read",
    response_model=notification_schemas.NotificationView,
)
def post_read(
    notification_id: int,
    session: _SessionDep,
    tourist: _TouristDep,
) -> notification_schemas.NotificationView:
    """Mark one notification as read (idempotent — first instant persists,
    FR-013); unknown/foreign id → 404 without leaking existence."""
    data = delivery_service.mark_read(
        session, tourist_id=tourist.account_id, notification_id=notification_id
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found")
    return _view(data)


@router.post("/read-all", response_model=notification_schemas.UnreadCountResponse)
def post_read_all(
    session: _SessionDep,
    tourist: _TouristDep,
) -> notification_schemas.UnreadCountResponse:
    """Mark ALL unread of the tourist as read (FR-013) → zero remaining."""
    delivery_service.mark_all(session, tourist_id=tourist.account_id)
    return notification_schemas.UnreadCountResponse.from_internal(unread_count=0)
