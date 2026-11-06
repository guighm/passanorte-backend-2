"""Chatbot sessions and messages (feature 016 — chatbot module).

Revision ID: 0011_chatbot_sessions
Revises: 0010_notifications
Create Date: 2026-11-06

Two new tables, owned exclusively by the ``chatbot`` module
(data-model.md §1):

- ``chat_sessions`` — one conversation of one tourist; no closure state
  (spec clarification Q1); FK → ``tourists.id`` is a read-only reference
  (constitution rule 4).
- ``chat_messages`` — one immutable message per row; ``role`` is
  ``'user'`` | ``'assistant'`` (application-enforced); ``itinerary`` is a
  nullable JSON snapshot with generation-moment display data (FR-025,
  clarification Q2/Q6). Messages only ever appear via the chatbot module's
  own service flow — no cross-domain writers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_chatbot_sessions"
down_revision: str | None = "0010_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tourist_id",
            sa.Integer(),
            sa.ForeignKey("tourists.id"),
            nullable=False,
            index=True,
        ),  # read-only tourists reference (constitution rule 4)
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False, index=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "itinerary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], name="fk_chat_messages_session_id_chat_sessions"
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
