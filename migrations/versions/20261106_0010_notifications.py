"""Interest-notification channel (feature 015 — notifications module).

Revision ID: 0010_notifications
Revises: 0009_access_events
Create Date: 2026-11-06

Two new tables, owned exclusively by the ``notifications`` module
(data-model.md §1–§2):

- ``notification_subscriptions`` — the tourist's own notification channel
  selection (Q1, independent of profile interests): unique per
  (tourist, category), idempotent subscribe (FR-005); index on
  ``category_key`` serves the set-based emission match (research R3).
- ``notifications`` — one row per tourist×item received; unique
  (tourist_id, item_type, item_id) enforces the FR-009 dedupe at the DB
  (inserts ride on_conflict_do_nothing — research R2/R3);
  ``ix_notifications_tourist_read`` (tourist_id, read_at) serves the unread
  list/filter/count (SC-005). ``read_at`` is a one-way transition
  (idempotent marking keeps the first instant — FR-013).

Emitters never write these tables directly — generation happens inside the
notifications public service seam (constitution rule 5, FR-008).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_notifications"
down_revision: str | None = "0009_access_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tourist_id",
            sa.Integer(),
            sa.ForeignKey("tourists.id"),
            nullable=False,
            index=True,
        ),  # read-only tourists reference (constitution rule 4)
        sa.Column("category_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tourist_id", "category_key", name="uq_notification_subscriptions"),
    )
    op.create_index(
        "ix_notification_subscriptions_category",
        "notification_subscriptions",
        ["category_key"],
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tourist_id",
            sa.Integer(),
            sa.ForeignKey("tourists.id"),
            nullable=False,
            index=True,
        ),  # read-only tourists reference (constitution rule 4)
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tourist_id",
            "item_type",
            "item_id",
            name="uq_notifications_tourist_item",
        ),
    )
    op.create_index("ix_notifications_tourist_read", "notifications", ["tourist_id", "read_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_tourist_read", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_notification_subscriptions_category", table_name="notification_subscriptions")
    op.drop_table("notification_subscriptions")
