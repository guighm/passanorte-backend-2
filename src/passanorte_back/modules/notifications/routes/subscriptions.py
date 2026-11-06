"""Subscription routes of the ``notifications`` module (feature 015).

Mounted on the canonical router (``MODULE_ROUTERS["notifications"]``, prefix
``/api/v1/notifications``); the tag comes exclusively from the central
registry via ``core/routers.py`` — no tag strings here (spec 006, FR-002).
Every endpoint is tourist-exclusive (``auth.services.require_tourist`` —
FR-001/RF03). Failures raise ``HTTPException`` → unified ``ApiError``
(spec 005).
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_tourist,
)
from passanorte_back.modules.notifications import schemas as notification_schemas
from passanorte_back.modules.notifications.services import (
    subscriptions as subscriptions_service,
)

router = MODULE_ROUTERS["notifications"]

_SessionDep = Annotated[Session, Depends(get_session)]
_TouristDep = Annotated[AuthenticatedUser, Depends(require_tourist)]


@router.get("/subscriptions", response_model=notification_schemas.SubscriptionsResponse)
def get_subscriptions(
    session: _SessionDep,
    tourist: _TouristDep,
) -> notification_schemas.SubscriptionsResponse:
    """Current notification-channel selection of the tourist (RF37, Q1)."""
    keys = subscriptions_service.list_subscriptions(session, tourist_id=tourist.account_id)
    return notification_schemas.SubscriptionsResponse.from_internal(category_keys=keys)


@router.put("/subscriptions", response_model=notification_schemas.SubscriptionsResponse)
def put_subscriptions(
    payload: notification_schemas.SubscriptionsUpdateRequest,
    session: _SessionDep,
    tourist: _TouristDep,
) -> notification_schemas.SubscriptionsResponse:
    """Replace the WHOLE notification-channel selection (FR-004); keys are
    validated against the city catalog (422 naming the invalid key — FR-005)."""
    keys = subscriptions_service.replace_subscriptions(
        session, tourist_id=tourist.account_id, category_keys=payload.category_keys
    )
    return notification_schemas.SubscriptionsResponse.from_internal(category_keys=keys)


@router.delete(
    "/subscriptions/{category_key}",
    response_model=notification_schemas.SubscriptionsResponse,
)
def delete_subscription(
    category_key: str,
    session: _SessionDep,
    tourist: _TouristDep,
) -> notification_schemas.SubscriptionsResponse:
    """Idempotent cancel of one category (FR-006): a non-subscribed valid
    key ends in the same 'not subscribed' state without error."""
    keys = subscriptions_service.cancel_subscription(
        session, tourist_id=tourist.account_id, category_key=category_key
    )
    return notification_schemas.SubscriptionsResponse.from_internal(category_keys=keys)
