"""HTTP-bound DTOs of the notifications module (all ``ApiModel``, feature 015)."""

from passanorte_back.modules.notifications.schemas.notifications import (
    NotificationsResponse,
    NotificationView,
    SubscriptionsResponse,
    SubscriptionsUpdateRequest,
    UnreadCountResponse,
)

__all__ = [
    "NotificationView",
    "NotificationsResponse",
    "SubscriptionsResponse",
    "SubscriptionsUpdateRequest",
    "UnreadCountResponse",
]
