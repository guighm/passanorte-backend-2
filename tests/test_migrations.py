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
            versions = [row[0] for row in conn.execute("SELECT * FROM alembic_version").fetchall()]
        else:
            versions = []
    finally:
        conn.close()
    return tables, versions


def test_upgrade_downgrade_reupgrade_on_empty_sqlite(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrations-test.db'}"

    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    tables_after_upgrade, versions_after_upgrade = _database_state(database_url)

    # Feature tables (auth + employees + tourists schema, data-model.md).
    # Only the feature-owned tables + Alembic state — no other business table.
    assert tables_after_upgrade == {
        "alembic_version",
        "admin_users",
        "employees",
        "auth_sessions",
        "tourists",
        "tourist_interests",
    }, tables_after_upgrade
    assert versions_after_upgrade == ["0003_tourists"]

    _assert_auth_schema(database_url)
    _assert_tourists_schema(database_url)

    downgrade = _alembic(database_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    tables_after_downgrade, versions_after_downgrade = _database_state(database_url)

    reupgrade = _alembic(database_url, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr

    tables_final, versions_final = _database_state(database_url)

    assert tables_after_downgrade == {"alembic_version"}, tables_after_downgrade
    assert versions_after_downgrade == []
    assert tables_final == {
        "alembic_version",
        "admin_users",
        "employees",
        "auth_sessions",
        "tourists",
        "tourist_interests",
    }
    assert versions_final == ["0003_tourists"]


def _assert_auth_schema(database_url: str) -> None:
    """T007: columns/unique constraints per data-model.md (§1–§3)."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        expected = {
            "admin_users": {
                "id",
                "username",
                "password_hash",
                "role",
                "is_active",
                "is_bootstrap",
                "created_at",
                "updated_at",
            },
            "employees": {
                "id",
                "name",
                "username",
                "password_hash",
                "role",
                "status",
                "created_at",
                "updated_at",
            },
            "auth_sessions": {
                "id",
                "account_type",
                "account_id",
                "refresh_token_hash",
                "created_at",
                "expires_at",
                "revoked_at",
            },
        }
        for table, columns in expected.items():
            names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            assert columns <= names, (table, names)
        # Unique usernames (per data-model.md: case-insensitive at service
        # level, unique index at database level) and unique refresh hash.
        for table in ("admin_users", "employees"):
            indexes = conn.execute(f"PRAGMA index_list({table})").fetchall()
            has_unique_username = any(
                row[2]
                and conn.execute(f"PRAGMA index_info({row[1]})").fetchall()[0][2] == "username"
                for row in indexes
                if row[2]
            )
            assert has_unique_username, table
        indexes = conn.execute("PRAGMA index_list(auth_sessions)").fetchall()
        has_unique_refresh_hash = any(
            row[2]
            and conn.execute(f"PRAGMA index_info({row[1]})").fetchall()[0][2]
            == "refresh_token_hash"
            for row in indexes
            if row[2]
        )
        assert has_unique_refresh_hash
    finally:
        conn.close()


def _assert_tourists_schema(database_url: str) -> None:
    """T006: columns/unique constraints per data-model.md (§1–§2)."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        expected = {
            "tourists": {
                "id",
                "first_name",
                "last_name",
                "country_of_origin",
                "email_encrypted",
                "email_lookup",
                "phone_encrypted",
                "cpf_encrypted",
                "cpf_lookup",
                "passport_encrypted",
                "passport_lookup",
                "password_hash",
                "created_at",
                "updated_at",
            },
            "tourist_interests": {
                "id",
                "tourist_id",
                "category_key",
            },
        }
        for table, columns in expected.items():
            names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            assert columns <= names, (table, names)
        # Unique lookups (equality/uniqueness without plaintext — RNF08).
        for table, column in (
            ("tourists", "email_lookup"),
            ("tourists", "cpf_lookup"),
            ("tourists", "passport_lookup"),
        ):
            indexes = conn.execute(f"PRAGMA index_list({table})").fetchall()
            has_unique = any(
                row[2] and conn.execute(f"PRAGMA index_info({row[1]})").fetchall()[0][2] == column
                for row in indexes
                if row[2]
            )
            assert has_unique, (table, column)
        unique_pairs = {
            tuple(row[2] for row in conn.execute(f"PRAGMA index_info({name})").fetchall())
            for _, name, on_unique in (
                (item[0], item[1], item[2])
                for item in conn.execute("PRAGMA index_list(tourist_interests)").fetchall()
            )
            if on_unique
        }
        assert ("tourist_id", "category_key") in unique_pairs, unique_pairs
    finally:
        conn.close()


def test_database_url_is_read_from_settings_not_hardcoded() -> None:
    """``migrations/env.py`` never hardcodes the URL — uses ``settings.database_url``."""
    env_py = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "settings.database_url" in env_py or "config = CONFIG" in env_py
    assert "postgresql://" not in env_py
    assert "sqlite://" not in env_py
