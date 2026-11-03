"""Gamification domain tables (feature 009-tourist-routes-gamification).

Revision ID: 0006_gamification
Revises: 0005_events
Create Date: 2026-11-02

The seven tables belong exclusively to the ``gamification`` module
(data-model §1): ``tourist_routes``, ``route_spots``, ``prizes``,
``route_enrollments``, ``spot_visits``, ``completion_badges`` and
``redemption_codes``. ``tourist_id``/``tourist_spot_id`` are read-only
references into ``tourists``/``tourist_spots`` (constitution rule 4 — the
only cross-domain touchpoints are public service functions, never these
rows).

Key uniqueness rules: partial unique index over active-route prize
bindings (Q1 — a prize is linkable to at most one active route); pair
uniqueness for enrollments/badges/codes (one reward per tourist-route
completion — SC-003) and for spot visits (idempotent per tourist-spot
pair). Stock can never be negative: quantity guards are conditional
UPDATEs at the service layer (research R4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_gamification"
down_revision: str | None = "0005_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_ROUTE_PRIZE_WHERE = sa.literal_column("removed_at IS NULL")


def upgrade() -> None:
    op.create_table(
        "prizes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_prizes_stock_non_negative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_prizes_reserved_non_negative"),
    )

    op.create_table(
        "tourist_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column(
            "prize_id",
            sa.Integer(),
            sa.ForeignKey("prizes.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Q1: one prize bound to at most one active route.
    op.create_index(
        "uq_tourist_routes_active_prize",
        "tourist_routes",
        ["prize_id"],
        unique=True,
        sqlite_where=_ACTIVE_ROUTE_PRIZE_WHERE,
        postgresql_where=_ACTIVE_ROUTE_PRIZE_WHERE,
    )

    op.create_table(
        "route_spots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "route_id",
            sa.Integer(),
            sa.ForeignKey("tourist_routes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tourist_spot_id", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tourist_spot_id"], ["tourist_spots.id"]
        ),  # read-only reference (constitution rule 4)
        sa.UniqueConstraint("route_id", "tourist_spot_id", name="uq_route_spots"),
    )

    op.create_table(
        "route_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False, index=True),
        sa.Column("tourist_id", sa.Integer(), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["tourist_routes.id"]),
        sa.ForeignKeyConstraint(["tourist_id"], ["tourists.id"]),
        sa.UniqueConstraint("route_id", "tourist_id", name="uq_route_enrollments"),
    )

    op.create_table(
        "spot_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tourist_id", sa.Integer(), nullable=False),
        sa.Column("tourist_spot_id", sa.Integer(), nullable=False),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tourist_id"], ["tourists.id"]),
        sa.ForeignKeyConstraint(["tourist_spot_id"], ["tourist_spots.id"]),
        sa.UniqueConstraint("tourist_id", "tourist_spot_id", name="uq_spot_visits"),
    )

    op.create_table(
        "completion_badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False, index=True),
        sa.Column("tourist_id", sa.Integer(), nullable=False, index=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["tourist_routes.id"]),
        sa.ForeignKeyConstraint(["tourist_id"], ["tourists.id"]),
        sa.UniqueConstraint("route_id", "tourist_id", name="uq_completion_badges"),
    )

    op.create_table(
        "redemption_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("route_id", sa.Integer(), nullable=False, index=True),
        sa.Column("tourist_id", sa.Integer(), nullable=False, index=True),
        sa.Column("prize_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pickup_spot_id", sa.Integer(), nullable=True),
        sa.Column("conceded_by", sa.String(150), nullable=True),
        sa.ForeignKeyConstraint(["route_id"], ["tourist_routes.id"]),
        sa.ForeignKeyConstraint(["tourist_id"], ["tourists.id"]),
        sa.ForeignKeyConstraint(["prize_id"], ["prizes.id"]),
        sa.ForeignKeyConstraint(["pickup_spot_id"], ["tourist_spots.id"]),
        sa.UniqueConstraint("route_id", "tourist_id", name="uq_redemption_codes"),
        sa.CheckConstraint("status IN ('unused', 'used')", name="ck_redemption_codes_status"),
    )


def downgrade() -> None:
    op.drop_table("redemption_codes")
    op.drop_table("completion_badges")
    op.drop_table("spot_visits")
    op.drop_table("route_enrollments")
    op.drop_table("route_spots")
    op.drop_index("uq_tourist_routes_active_prize", table_name="tourist_routes")
    op.drop_table("tourist_routes")
    op.drop_table("prizes")
