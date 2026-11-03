"""Visitation domain table + tourists-spot tolerance radius (feature 011).

Revision ID: 0007_visitation
Revises: 0006_gamification
Create Date: 2026-11-03

One new table, owned exclusively by the ``visitation`` module
(data-model.md §1): ``visitations`` — the append-only immutable ledger of
validated visits. ``tourist_id``/``tourist_spot_id`` are read-only
references into ``tourists``/``tourist_spots`` (constitution rule 4 —
cross-module touchpoints are public service functions, never these rows).
Intentionally NO uniqueness on the (tourist, spot) pair: repeated valid
visits append additional rows (spec Edge Cases, clarification Q5 — no
throttle); "visited" is a projection derived from the ledger (Q1), and the
timestamp is captured server-side in UTC (research R8).

Also adds the nullable ``tolerance_radius_m`` column on ``tourist_spots``
— a table the ``tourist_spots`` module already owns (data-model §2):
the per-spot override of the presence radius in meters; ``NULL`` falls
back to ``settings.gps_tolerance_radius_m`` (100.0 default, research R2).
Coordinates are stored in cleartext on purpose (clarification Q7 —
operational data outside the sensitive-field census of the constitution).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_visitation"
down_revision: str | None = "0006_gamification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tourist_id", sa.Integer(), nullable=False, index=True),
        sa.Column(
            "tourist_spot_id",
            sa.Integer(),
            sa.ForeignKey("tourist_spots.id"),
            nullable=False,
            index=True,
        ),  # read-only references (constitution rule 4)
        sa.Column(
            "visited_at", sa.DateTime(timezone=True), nullable=False, index=True
        ),  # history ordering (data-model.md §1)
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
    )
    op.add_column(
        "tourist_spots", sa.Column("tolerance_radius_m", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tourist_spots", "tolerance_radius_m")
    op.drop_table("visitations")
