"""Discovery feed active-spots index (feature 013).

Revision ID: 0008_spot_discovery_index
Revises: 0007_visitation
Create Date: 2026-11-03

Schema change is a single partial index supporting the discovery feed's
candidate query (research.md §R3): active spots =
``removed_at IS NULL AND status != 'permanently_closed'`` (data-model.md).
``ix_tourist_spot_status_active`` covers ``tourist_spots(status)`` filtered
to non-removed rows. Partial indexes are supported identically by SQLite
and PostgreSQL (RNF17 dual environment). No table or column changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_spot_discovery_index"
down_revision: str | None = "0007_visitation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_tourist_spot_status_active",
        "tourist_spots",
        ["status"],
        unique=False,
        sqlite_where=sa.text("removed_at IS NULL"),
        postgresql_where=sa.text("removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tourist_spot_status_active", table_name="tourist_spots")
