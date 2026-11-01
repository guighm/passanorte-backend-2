"""Tourist domain tables (feature 003-turistas-perfil, data-model.md).

Revision ID: 0003_tourists
Revises: 0002_auth_accounts
Create Date: 2026-10-31

``tourists`` / ``tourist_interests`` belong to the ``tourists`` module (no
cross-domain FK — constitution rule 4). Sensitive fields are stored
encrypted (``*_encrypted``) with keyed-hash lookup sisters (``*_lookup``)
for equality/uniqueness — never plaintext (RNF08). Unique lookups are valid
only among tourists (clar. s1-Q1 — admin/employee accounts are out of
scope). Document rule (cpf XOR passport) is enforced at service level.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tourists"
down_revision: str | None = "0002_auth_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tourists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("country_of_origin", sa.String(100), nullable=False),
        sa.Column("email_encrypted", sa.String(), nullable=False),
        sa.Column("email_lookup", sa.String(64), nullable=False, unique=True),
        sa.Column("phone_encrypted", sa.String(), nullable=False),
        sa.Column("cpf_encrypted", sa.String(), nullable=True),
        sa.Column("cpf_lookup", sa.String(64), nullable=True, unique=True),
        sa.Column("passport_encrypted", sa.String(), nullable=True),
        sa.Column("passport_lookup", sa.String(64), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tourists_email_lookup", "tourists", ["email_lookup"])
    op.create_index("ix_tourists_cpf_lookup", "tourists", ["cpf_lookup"])
    op.create_index("ix_tourists_passport_lookup", "tourists", ["passport_lookup"])

    op.create_table(
        "tourist_interests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tourist_id", sa.Integer(), nullable=False, index=True),
        sa.Column("category_key", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["tourist_id"], ["tourists.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tourist_id", "category_key", name="uq_tourist_interests"),
    )


def downgrade() -> None:
    op.drop_table("tourist_interests")
    op.drop_index("ix_tourists_passport_lookup", table_name="tourists")
    op.drop_index("ix_tourists_cpf_lookup", table_name="tourists")
    op.drop_index("ix_tourists_email_lookup", table_name="tourists")
    op.drop_table("tourists")
