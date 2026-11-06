"""Delivery services of the notifications module (feature 015, RF37).

Polling-only delivery (RNF15): the most-recent list with the unread total
regardless of filter (Q4), the cheap unread-count probe (Q5/FR-013a) and
the idempotent read marking (first instant persists, FR-013). Ownership is
the authenticated tourist (foreign/unknown → 404 semantics, no leak).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from passanorte_back.modules.notifications.repositories.notifications import (
    count_unread,
    get_for_tourist,
    list_for_tourist,
    mark_all_read,
    mark_read_idempotent,
)

_UNREAD_LIST_LIMIT = 50  # Q4 fixed most-recent limit (documented, research R6)


def _as_utc(moment: datetime | None) -> datetime | None:
    """UTC-aware instant (SQLite reloads naive datetimes — research R2)."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


def list_notifications(
    session: Session, *, tourist_id: int, only_unread: bool
) -> dict[str, object]:
    """Most-recent list (default: only unread) with the tourist's complete
    unread total (contracts §2, Q4)."""
    items, unread_total = list_for_tourist(
        session, tourist_id=tourist_id, only_unread=only_unread, limit=_UNREAD_LIST_LIMIT
    )
    return {
        "unread_count": unread_total,
        "items": [
            {
                "id": item.id,
                "item_type": item.item_type,
                "item_id": item.item_id,
                "title": item.title,
                "description": item.description,
                "created_at": _as_utc(item.created_at),
                "read_at": _as_utc(item.read_at),
            }
            for item in items
        ],
    }


def unread_count(session: Session, *, tourist_id: int) -> int:
    """Total unread of the tourist (FR-013a — cheap polling probe)."""
    return count_unread(session, tourist_id=tourist_id)


def mark_read(
    session: Session, *, tourist_id: int, notification_id: int
) -> dict[str, object] | None:
    """Idempotent mark-as-read of an OWN notification (FR-013).

    Unknown id or another tourist's id → ``None`` (route turns it into 404
    without leaking existence).
    """
    notification = get_for_tourist(session, tourist_id=tourist_id, notification_id=notification_id)
    if notification is None:
        return None
    marked = mark_read_idempotent(session, notification)
    return {
        "id": marked.id,
        "item_type": marked.item_type,
        "item_id": marked.item_id,
        "title": marked.title,
        "description": marked.description,
        "created_at": _as_utc(marked.created_at),
        "read_at": _as_utc(marked.read_at),
    }


def mark_all(session: Session, *, tourist_id: int) -> int:
    """Mark everything unread of the tourist (FR-013 read-all); returns
    the number of notifications marked."""
    return mark_all_read(session, tourist_id=tourist_id)
