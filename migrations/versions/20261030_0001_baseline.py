"""Baseline vazio da fundação (FR-007 — nenhuma tabela de negócio).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-30

Estabelece o fluxo de migrations versionadas sem inventar schema: up/down são
idempotentes e não realizam operações. Features futuras adicionam revisions
próprias a partir desta.
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass  # baseline vazio — nada a criar


def downgrade() -> None:
    pass  # baseline vazio — nada a reverter
