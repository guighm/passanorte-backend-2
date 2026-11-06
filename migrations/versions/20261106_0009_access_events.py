"""Access log of tourist-authenticated requests (feature 014 — dashboard).

Revision ID: 0009_access_events
Revises: 0008_spot_discovery_index
Create Date: 2026-11-06

One new ``access_events`` table, owned exclusively by the ``dashboard``
module (data-model.md §1): the append-only ledger of tourist requests
(FR-008 — best-effort insert, FR-022). ``day`` is precomputed in the
configured city timezone (RNF06) at recording time so the "unique tourists
per day" metric is a plain indexed ``COUNT(DISTINCT tourist_id) GROUP BY
day`` — set-based SQL, never Python loops (FR-020, research R3).
Intentionally NO unique constraint on (tourist_id, day): repeated requests
on the same day each append a row; uniqueness lives in the query.
Retention/expurgo is out of scope this phase (spec Deferred).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_access_events"
down_revision: str | None = "0008_spot_discovery_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tourist_id",
            sa.Integer(),
            sa.ForeignKey("tourists.id"),
            nullable=False,
            index=True,
        ),  # read-only tourists reference (constitution rule 4)
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
    )
    op.create_index("ix_access_events_at", "access_events", ["occurred_at"], unique=False)
    op.create_index("ix_access_events_day", "access_events", ["day"], unique=False)
    op.create_index(
        "ix_access_events_tourist_day",
        "access_events",
        ["tourist_id", "day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_access_events_tourist_day", table_name="access_events")
    op.drop_index("ix_access_events_day", table_name="access_events")
    op.drop_index("ix_access_events_at", table_name="access_events")
    op.drop_table("access_events")
