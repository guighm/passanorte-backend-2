"""Notification ledger persistence (feature 015 — data-model.md §2).

Append-only received items plus the one-way read-state transition
(``read_at NULL → instant``, idempotent — FR-013). The tourist×item dedupe
is the DB unique constraint + ``on_conflict_do_nothing`` insert (portable
SQLite/PostgreSQL — research R2/R3); the unread list/count ride
``ix_notifications_tourist_read``.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

TITLE_LENGTH = 200
DESCRIPTION_LENGTH = 300
ITEM_TYPE_LENGTH = 20


class Notification(Base):
    """One notification received by one tourist about one item."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "tourist_id", "item_type", "item_id", name="uq_notifications_tourist_item"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(
        ForeignKey("tourists.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(ITEM_TYPE_LENGTH))
    item_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(TITLE_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


def insert_notifications(session: Session, *, rows: list[dict]) -> int:
    """Bulk insert deduping against the unique tourist×item constraint.

    Returns the number of rows ACTUALLY inserted (matches on conflict are
    skipped — a re-emission for the same item is a no-op, FR-009).
    """
    if not rows:
        return 0
    dialect_name = session.bind.dialect.name
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        statement = (
            insert(Notification)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["tourist_id", "item_type", "item_id"])
        )
    else:  # sqlite (tests/ephemeral databases share the ON CONFLICT syntax)
        from sqlalchemy.dialects.sqlite import insert

        statement = (
            insert(Notification)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["tourist_id", "item_type", "item_id"])
        )
    result = session.execute(statement)
    return int(result.rowcount or 0)


def list_for_tourist(
    session: Session,
    *,
    tourist_id: int,
    only_unread: bool,
    limit: int,
) -> tuple[list[Notification], int]:
    """(items, unread_total): most-recent first, fixed limit (Q4).

    ``unread_total`` is the tourist's complete unread count REGARDLESS of
    the filter/limit (contracts §2).
    """
    unread_total = int(
        session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.tourist_id == tourist_id,
                Notification.read_at.is_(None),
            )
        ).scalar_one()
    )
    conditions = [Notification.tourist_id == tourist_id]
    if only_unread:
        conditions.append(Notification.read_at.is_(None))
    items = (
        session.query(Notification)
        .filter(*conditions)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )
    return list(items), unread_total


def count_unread(session: Session, *, tourist_id: int) -> int:
    """Cheap polling probe (FR-013a/Q5)."""
    return int(
        session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.tourist_id == tourist_id,
                Notification.read_at.is_(None),
            )
        ).scalar_one()
    )


def get_for_tourist(
    session: Session, *, tourist_id: int, notification_id: int
) -> Notification | None:
    """Own-notification lookup (foreign/unknown → None — no leak, R6)."""
    return (
        session.query(Notification)
        .filter(
            Notification.tourist_id == tourist_id,
            Notification.id == notification_id,
        )
        .one_or_none()
    )


def mark_read_idempotent(session: Session, notification: Notification) -> Notification:
    """One-way transition: the FIRST read instant persists (FR-013)."""
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        session.flush()
    return notification


def mark_all_read(session: Session, *, tourist_id: int) -> int:
    """Set the unread rows' read_at once; returns the rows marked."""
    rows = (
        session.query(Notification)
        .filter(
            Notification.tourist_id == tourist_id,
            Notification.read_at.is_(None),
        )
        .all()
    )
    changed = 0
    for row in rows:
        row.read_at = datetime.now(UTC)
        changed += 1
    if changed:
        session.flush()
    return changed
