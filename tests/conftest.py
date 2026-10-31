"""Global test configuration: fixed, synthetic environment.

Fixes DATABASE_URL (in-memory SQLite) and a synthetic JWT_SECRET — never a
real secret (Quality Gate: no sensitive data in tests, FR-011). Tests that
need another profile override via monkeypatch.
"""

import os

import pytest

TEST_DATABASE_URL = "sqlite:///:memory:"
TEST_JWT_SECRET = "test-only-synthetic-secret-not-real"

# Essentials also at module level (collection time): test modules importing
# ``passanorte_back.main`` (and, indirectly, ``core.db``, which builds
# Settings) run before any fixture.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def _test_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthetic essential environment for every test (autouse)."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    # Isolate the tests from any .env present in the checkout.
    monkeypatch.delenv("JWT_TTL", raising=False)
    monkeypatch.delenv("GPS_TOLERANCE_RADIUS_M", raising=False)
    monkeypatch.delenv("CITY_NAME", raising=False)
    monkeypatch.delenv("ENABLED_LANGUAGES", raising=False)
    monkeypatch.delenv("LOCATION_DATA_PATH", raising=False)
    assert os.environ["DATABASE_URL"] == TEST_DATABASE_URL
