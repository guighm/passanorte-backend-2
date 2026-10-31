"""Auth and access control tables (feature 002-auth-rbac, data-model.md).

Revision ID: 0002_auth_accounts
Revises: 0001_baseline
Create Date: 2026-10-31

admin_users / auth_sessions belong to the ``auth`` module; employees to the
``employees`` module (no cross-domain FK — constitution rule 4; the
auth_sessions.account_id points to one of the two account tables by
``account_type``). Username uniqueness is a database-level unique index;
case-insensitive comparison is a service-level rule (data-model.md).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_accounts"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_bootstrap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"])

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="employee"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employees_username", "employees", ["username"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_type", sa.String(10), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False, index=True),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_sessions_account", "auth_sessions", ["account_type", "account_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_account", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_employees_username", table_name="employees")
    op.drop_table("employees")
    op.drop_index("ix_admin_users_username", table_name="admin_users")
    op.drop_table("admin_users")
