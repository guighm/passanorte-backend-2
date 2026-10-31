"""Integration: versioned, portable persistence (FR-015/FR-016, SC-003).

``upgrade head`` over an empty database succeeds; ``downgrade base``
reverts; re-``upgrade`` reapplies. The database contains only
``alembic_version`` — no business table (FR-007).
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``alembic`` with a test-isolated database URL.

    Isolated subprocess: the test process env already fixes DATABASE_URL
    via conftest — here we pass the temporary database URL explicitly.
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
    """(tables, applied revisions) of the SQLite file database."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    if not path:
        return {":memory:"}, 0  # should never happen in this test
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

    # SC-003: only Alembic state — no business table.
    # (Alembic keeps its own ``alembic_version`` table after a base
    # downgrade; "revert" in Alembic terms means zeroing the revisions.)
    assert tables_after_upgrade == {"alembic_version"}, tables_after_upgrade
    assert applied_after_upgrade == 1
    assert tables_after_downgrade == {"alembic_version"}, tables_after_downgrade
    assert applied_after_downgrade == 0
    assert tables_final == {"alembic_version"}
    assert applied_final == 1


def test_database_url_is_read_from_settings_not_hardcoded() -> None:
    """``migrations/env.py`` never hardcodes the URL — uses ``settings.database_url``."""
    env_py = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "settings.database_url" in env_py or "config = CONFIG" in env_py
    assert "postgresql://" not in env_py
    assert "sqlite://" not in env_py
