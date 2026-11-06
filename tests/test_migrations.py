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

    # Feature tables (auth + employees + tourists + tourist_spots schema +
    # events + gamification, data-model.md). Only the feature-owned tables +
    # Alembic state — no other business table.
    assert tables_after_upgrade == {
        "alembic_version",
        "admin_users",
        "employees",
        "auth_sessions",
        "tourists",
        "tourist_interests",
        "tourist_spots",
        "tourist_spot_categories",
        "tourist_spot_schedule_entries",
        "events",
        # gamification (feature 009):
        "prizes",
        "tourist_routes",
        "route_spots",
        "route_enrollments",
        "spot_visits",
        "completion_badges",
        "redemption_codes",
        # visitation (feature 011):
        "visitations",
        # access events (feature 014 — dashboard):
        "access_events",
        # notifications (feature 015):
        "notification_subscriptions",
        "notifications",
        # chatbot (feature 016):
        "chat_sessions",
        "chat_messages",
    }, tables_after_upgrade
    assert versions_after_upgrade == ["0011_chatbot_sessions"]

    _assert_auth_schema(database_url)
    _assert_tourists_schema(database_url)
    _assert_tourist_spots_schema(database_url)
    _assert_events_schema(database_url)
    _assert_access_events_schema(database_url)
    _assert_notifications_schema(database_url)

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
        "tourist_spots",
        "tourist_spot_categories",
        "tourist_spot_schedule_entries",
        "events",
        # gamification (feature 009):
        "prizes",
        "tourist_routes",
        "route_spots",
        "route_enrollments",
        "spot_visits",
        "completion_badges",
        "redemption_codes",
        # visitation (feature 011):
        "visitations",
        # access events (feature 014 — dashboard):
        "access_events",
        # notifications (feature 015):
        "notification_subscriptions",
        "notifications",
        # chatbot (feature 016):
        "chat_sessions",
        "chat_messages",
    }
    assert versions_final == ["0011_chatbot_sessions"]


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


def _assert_access_events_schema(database_url: str) -> None:
    """Feature 014: access_events columns + indexes (data-model.md §1)."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        names = {row[1] for row in conn.execute("PRAGMA table_info(access_events)").fetchall()}
        assert names >= {
            "id",
            "tourist_id",
            "occurred_at",
            "day",
        }, names
        # Indexes: single time columns + (tourist_id, day) composite —
        # research R3, set-based COUNT(DISTINCT) GROUP BY day needs them.
        index_pairs = {
            tuple(row[2] for row in conn.execute(f"PRAGMA index_info({name})").fetchall())
            for name in (
                row[1] for row in conn.execute("PRAGMA index_list(access_events)").fetchall()
            )
        }
        assert ("tourist_id",) in index_pairs, index_pairs
        assert ("occurred_at",) in index_pairs, index_pairs
        assert ("day",) in index_pairs, index_pairs
        assert ("tourist_id", "day") in index_pairs, index_pairs
    finally:
        conn.close()


def _assert_notifications_schema(database_url: str) -> None:
    """Feature 015: subscription/notification columns + constraints."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        subs = {
            row[1]
            for row in conn.execute("PRAGMA table_info(notification_subscriptions)").fetchall()
        }
        assert subs >= {"id", "tourist_id", "category_key", "created_at"}, subs
        notifs = {row[1] for row in conn.execute("PRAGMA table_info(notifications)").fetchall()}
        assert notifs >= {
            "id",
            "tourist_id",
            "item_type",
            "item_id",
            "title",
            "description",
            "created_at",
            "read_at",
        }, notifs
        sub_pairs = {
            tuple(row[2] for row in conn.execute(f"PRAGMA index_info({name})").fetchall())
            for name in (
                row[1]
                for row in conn.execute("PRAGMA index_list(notification_subscriptions)").fetchall()
            )
        }
        assert ("tourist_id", "category_key") in sub_pairs, sub_pairs
        assert ("category_key",) in sub_pairs, sub_pairs
        notif_indexes = {
            tuple(row[2] for row in conn.execute(f"PRAGMA index_info({name})").fetchall())
            for name in (
                row[1] for row in conn.execute("PRAGMA index_list(notifications)").fetchall()
            )
        }
        assert ("tourist_id", "read_at") in notif_indexes, notif_indexes
        assert ("tourist_id", "item_type", "item_id") in notif_indexes, notif_indexes
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


def _assert_tourist_spots_schema(database_url: str) -> None:
    """Feature 007 T003: columns/unique constraints per feature data-model §2."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        expected = {
            "tourist_spots": {
                "id",
                "name",
                "description",
                "latitude",
                "longitude",
                "status",
                "removed_at",
                "created_at",
                "updated_at",
            },
            "tourist_spot_categories": {
                "id",
                "spot_id",
                "category_key",
            },
            "tourist_spot_schedule_entries": {
                "id",
                "spot_id",
                "weekday",
                "opens_at",
                "closes_at",
            },
        }
        for table, columns in expected.items():
            names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            assert columns <= names, (table, names)
        unique_pairs = {
            tuple(row[2] for row in conn.execute(f"PRAGMA index_info({name})").fetchall())
            for _, name, on_unique in (
                (item[0], item[1], item[2])
                for item in conn.execute("PRAGMA index_list(tourist_spot_categories)").fetchall()
            )
            if on_unique
        }
        assert ("spot_id", "category_key") in unique_pairs, unique_pairs
    finally:
        conn.close()


def _assert_events_schema(database_url: str) -> None:
    """Feature 008 T001: columns per feature data-model §1 (exact-money
    integer cents, FK to tourist spots with cascade)."""
    import sqlite3

    path = database_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        names = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        assert {
            "id",
            "spot_id",
            "occurrence_date",
            "description",
            "ticket_price_cents",
            "created_at",
            "updated_at",
        } <= names, names
        foreign_keys = conn.execute("PRAGMA foreign_key_list(events)").fetchall()
        targets = {(row[2], row[3], row[4]) for row in foreign_keys}
        assert ("tourist_spots", "spot_id", "id") in targets, targets
        cascade = any(row[6] == "CASCADE" for row in foreign_keys)
        assert cascade, foreign_keys
    finally:
        conn.close()


def test_database_url_is_read_from_settings_not_hardcoded() -> None:
    """``migrations/env.py`` never hardcodes the URL — uses ``settings.database_url``."""
    env_py = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "settings.database_url" in env_py or "config = CONFIG" in env_py
    assert "postgresql://" not in env_py
    assert "sqlite://" not in env_py
