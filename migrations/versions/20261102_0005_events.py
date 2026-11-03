"""Events domain table (feature 008-event-management).

Revision ID: 0005_events
Revises: 0004_tourist_spots
Create Date: 2026-11-02

``events`` belongs exclusively to the ``events`` module; ``spot_id`` is a
read-only reference to ``tourist_spots.id`` (constitution rule 4 — the only
cross-domain touchpoints are public service functions, never these rows).
The ticket price is stored as exact integer cents (research R1 — never
float, zero means free). Removal is physical (hard delete): the cascade
contract removes the spot's events together with the spot (clarification
2 of session 2026-11-02), so no soft-delete column exists here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_events"
down_revision: str | None = "0004_tourist_spots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spot_id", sa.Integer(), nullable=False, index=True),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("ticket_price_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["spot_id"], ["tourist_spots.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_events_occurrence_date", "events", ["occurrence_date"])


def downgrade() -> None:
    op.drop_table("events")
