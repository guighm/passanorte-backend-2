"""HTTP DTOs of the ``notifications`` module (feature 015 — contracts/notifications.md).

All schemas inherit the shared ``ApiModel`` (spec 005): JSON keys camelCase
(``categoryKeys``, ``itemType``, ``unreadCount``…), Python attributes
snake_case (PEP 8), strict input border (``extra="forbid"``, no
``populate_by_name``). Construction uses ``ApiModel.from_internal``.
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from passanorte_back.core.schemas import ApiModel


class SubscriptionsUpdateRequest(ApiModel):
    """PUT /subscriptions — whole-selection replace (FR-004, Q1)."""

    category_keys: Annotated[list[str], Field(min_length=0)]


class SubscriptionsResponse(ApiModel):
    """GET/PUT/DELETE /subscriptions — current selection (insertion order)."""

    category_keys: list[str]


class NotificationView(ApiModel):
    """One received notification (FR-014): presentable + deep-link pair."""

    id: int
    item_type: str
    item_id: int
    title: str
    description: str
    created_at: datetime
    read_at: datetime | None


class NotificationsResponse(ApiModel):
    """GET /notifications — most recent first with the unread total (Q4)."""

    unread_count: int = Field(ge=0)
    items: list[NotificationView]


class UnreadCountResponse(ApiModel):
    """GET /notifications/unread-count · POST read-all (Q5/FR-013a)."""

    unread_count: int = Field(ge=0)
