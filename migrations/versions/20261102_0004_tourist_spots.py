"""Tourist spot domain tables (feature 007-tourist-spots-management).

Revision ID: 0004_tourist_spots
Revises: 0003_tourists
Create Date: 2026-11-02

``tourist_spots`` / ``tourist_spot_categories`` /
``tourist_spot_schedule_entries`` belong to the ``tourist_spots`` module
(no cross-domain FK — constitution rule 4). Categories are persisted as
canonical keys validated against the configuration catalog at write time —
there is no catalog table (clarification Q1). Removal is a soft delete
(``removed_at``): rows survive, queries filter actives (research R6).
Weekdays are stored as ISO-8601 integers (1=monday..7=sunday), contracted
as day-name strings (research R4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tourist_spots"
down_revision: str | None = "0003_tourists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tourist_spots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tourist_spots_removed_at", "tourist_spots", ["removed_at"])

    op.create_table(
        "tourist_spot_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spot_id", sa.Integer(), nullable=False, index=True),
        sa.Column("category_key", sa.String(50), nullable=False, index=True),
        sa.ForeignKeyConstraint(["spot_id"], ["tourist_spots.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("spot_id", "category_key", name="uq_tourist_spot_categories"),
    )

    op.create_table(
        "tourist_spot_schedule_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spot_id", sa.Integer(), nullable=False, index=True),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(["spot_id"], ["tourist_spots.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("tourist_spot_schedule_entries")
    op.drop_table("tourist_spot_categories")
    op.drop_index("ix_tourist_spots_removed_at", table_name="tourist_spots")
    op.drop_table("tourist_spots")
