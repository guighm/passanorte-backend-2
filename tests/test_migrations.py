"""Integração: persistência versionada e portável (FR-015/FR-016, SC-003).

``upgrade head`` sobre banco vazio conclui; ``downgrade base`` reverte;
re-``upgrade`` reaplica. O banco contém apenas ``alembic_version`` — nenhuma
tabela de negócio (FR-007).
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Roda ``alembic -m`` com a URL do banco isolada do teste.

    Subprocesso isolado: a env do processo de teste já fixa DATABASE_URL via
    conftest — aqui passamos a URL do banco temporário explicitamente.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            *args,
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        timeout=120,
    )


def _database_state(database_url: str) -> tuple[set[str], int]:
    """(tabelas, revisions aplicados) do banco de arquivo SQLite."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    if not path:
        return {":memory:"}, 0  # nunca deve acontecer neste teste
    conn = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "alembic_version" in tables:
            applied = len(conn.execute("SELECT * FROM alembic_version").fetchall())
        else:
            applied = 0
    finally:
        conn.close()
    return tables, applied


def test_upgrade_downgrade_reupgrade_on_empty_sqlite(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrations-test.db'}"

    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    tables_after_upgrade, applied_after_upgrade = _database_state(database_url)

    downgrade = _alembic(database_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    tables_after_downgrade, applied_after_downgrade = _database_state(database_url)

    reupgrade = _alembic(database_url, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr

    tables_final, applied_final = _database_state(database_url)

    # SC-003: apenas o estado do Alembic — nenhuma tabela de negócio.
    # (Alembic mantém a própria tabela ``alembic_version`` após o downgrade
    # base; "reverter" em termos de Alembico significa zerar as revisions.)
    assert tables_after_upgrade == {"alembic_version"}, tables_after_upgrade
    assert applied_after_upgrade == 1
    assert tables_after_downgrade == {"alembic_version"}, tables_after_downgrade
    assert applied_after_downgrade == 0
    assert tables_final == {"alembic_version"}
    assert applied_final == 1


def test_database_url_is_read_from_settings_not_hardcoded() -> None:
    """``migrations/env.py`` nunca hardcodea URL — usa ``settings.database_url``."""
    env_py = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "settings.database_url" in env_py or "config = CONFIG" in env_py
    assert "postgresql://" not in env_py
    assert "sqlite://" not in env_py
