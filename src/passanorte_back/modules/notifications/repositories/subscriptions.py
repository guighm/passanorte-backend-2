"""Notification subscription persistence (feature 015 — data-model.md §1).

The table's data access belongs exclusively to the ``notifications``
domain. Rows are created/replaced/canceled only through this module's
services; emitters never touch it (constitution rule 5). The match query
for emission is a single set-based DISTINCT over the category index
(research R3) — no row loops (FR-020 analog).
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

CATEGORY_KEY_LENGTH = 100


class NotificationSubscription(Base):
    """One category of the tourist's notification channel selection."""

    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        UniqueConstraint("tourist_id", "category_key", name="uq_notification_subscriptions"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(
        ForeignKey("tourists.id", ondelete="CASCADE"), index=True
    )
    category_key: Mapped[str] = mapped_column(String(CATEGORY_KEY_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


def add_subscription(session: Session, *, tourist_id: int, category_key: str) -> None:
    """Insert one selection row (idempotent by unique constraint)."""
    session.add(NotificationSubscription(tourist_id=tourist_id, category_key=category_key))


def delete_subscriptions_not_in(session: Session, *, tourist_id: int, keep_keys: list[str]) -> int:
    """Remove the tourist's rows absent from ``keep_keys`` (replace path)."""
    if not keep_keys:
        return (
            session.query(NotificationSubscription)
            .filter(NotificationSubscription.tourist_id == tourist_id)
            .delete()
        )
    return (
        session.query(NotificationSubscription)
        .filter(
            NotificationSubscription.tourist_id == tourist_id,
            NotificationSubscription.category_key.not_in(keep_keys),
        )
        .delete(synchronize_session=False)
    )


def delete_subscription(session: Session, *, tourist_id: int, category_key: str) -> int:
    """Remove one selection row; returns 0 when it does not exist (Q1)."""
    return (
        session.query(NotificationSubscription)
        .filter(
            NotificationSubscription.tourist_id == tourist_id,
            NotificationSubscription.category_key == category_key,
        )
        .delete(synchronize_session=False)
    )


def keys_for_tourist(session: Session, *, tourist_id: int) -> list[str]:
    """Current selection, in insertion order (contracts §1)."""
    rows = (
        session.query(NotificationSubscription)
        .filter(NotificationSubscription.tourist_id == tourist_id)
        .order_by(NotificationSubscription.id)
        .all()
    )
    return [row.category_key for row in rows]


def subscribed_tourist_ids_for_categories(
    session: Session, *, category_keys: list[str]
) -> list[int]:
    """Distinct tourists subscribed to ANY of the keys (research R3)."""
    if not category_keys:
        return []
    rows = session.execute(
        select(NotificationSubscription.tourist_id)
        .where(NotificationSubscription.category_key.in_(category_keys))
        .distinct()
        .order_by(NotificationSubscription.tourist_id)
    )
    return [row[0] for row in rows]
