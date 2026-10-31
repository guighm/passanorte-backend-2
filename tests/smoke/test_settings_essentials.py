"""Smoke: essential Settings (FR-010/FR-011/FR-012).

Missing DATABASE_URL or JWT_SECRET interrupts Settings construction with a
message naming the field. No defaults for the two essentials.
"""

import pytest
from pydantic import ValidationError

from passanorte_back.core.config import Settings


def test_missing_database_url_fails_naming_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "database_url" in str(exc.value)


def test_missing_jwt_secret_fails_naming_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "jwt_secret" in str(exc.value)


def test_empty_jwt_secret_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "jwt_secret" in str(exc.value)


def test_empty_database_url_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "  ")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "database_url" in str(exc.value)


def test_both_essentials_present_builds_ok() -> None:
    settings = Settings()
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.jwt_secret  # synthetic from conftest, never real
