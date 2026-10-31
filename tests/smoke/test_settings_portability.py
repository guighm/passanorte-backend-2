"""Smoke: portabilidade de configuração (FR-010/FR-012/FR-013; data-model).

Defaults aplicados, resolved_city()/resolved_languages() lendo
config/location.json, override por ambiente e erros para valores inválidos.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from passanorte_back.core.config import LocationDataError, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCATION_FILE = REPO_ROOT / "config" / "location.json"


def test_documented_defaults_applied() -> None:
    settings = Settings()
    assert settings.jwt_ttl == 3600
    assert settings.gps_tolerance_radius_m == 100.0


def test_resolved_values_come_from_location_data() -> None:
    settings = Settings(location_data_path=LOCATION_FILE)
    data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
    assert settings.resolved_city() == data["city"]
    assert settings.resolved_languages() == data["languages"]


def test_env_overrides_beat_defaults_and_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_TTL", "7200")
    monkeypatch.setenv("GPS_TOLERANCE_RADIUS_M", "55.5")
    monkeypatch.setenv("CITY_NAME", "Caxambu")
    monkeypatch.setenv("ENABLED_LANGUAGES", '["pt-BR","en"]')
    settings = Settings(location_data_path=LOCATION_FILE)

    assert settings.jwt_ttl == 7200
    assert settings.gps_tolerance_radius_m == 55.5
    assert settings.resolved_city() == "Caxambu"
    assert settings.resolved_languages() == ["pt-BR", "en"]


def test_non_positive_jwt_ttl_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_TTL", "0")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "jwt_ttl" in str(exc.value)


def test_non_positive_gps_radius_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GPS_TOLERANCE_RADIUS_M", "-1")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "gps_tolerance_radius_m" in str(exc.value)


def test_explicitly_empty_languages_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLED_LANGUAGES", "[]")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "languages" in str(exc.value)


def test_missing_location_file_fails_with_clear_message(tmp_path: Path) -> None:
    settings = Settings(location_data_path=tmp_path / "nao-existe.json")
    with pytest.raises(LocationDataError) as exc:
        settings.resolved_city()
    assert "nao-existe.json" in str(exc.value)


def test_invalid_location_file_fails_with_clear_message(tmp_path: Path) -> None:
    bad = tmp_path / "location.json"
    bad.write_text("{não é json", encoding="utf-8")
    settings = Settings(location_data_path=bad)
    with pytest.raises(LocationDataError) as exc:
        settings.resolved_languages()
    assert "location.json" in str(exc.value)


def test_location_file_without_required_keys_fails(tmp_path: Path) -> None:
    incomplete = tmp_path / "location.json"
    incomplete.write_text('{"city": "Passa Quatro"}', encoding="utf-8")
    settings = Settings(location_data_path=incomplete)
    with pytest.raises(LocationDataError) as exc:
        settings.resolved_languages()
    assert "languages" in str(exc.value)


def test_empty_languages_in_file_fails(tmp_path: Path) -> None:
    empty = tmp_path / "location.json"
    empty.write_text('{"city": "X", "languages": []}', encoding="utf-8")
    settings = Settings(location_data_path=empty)
    with pytest.raises(LocationDataError) as exc:
        settings.resolved_languages()
    assert "languages" in str(exc.value)


def test_location_data_path_default_points_to_repo_config() -> None:
    settings = Settings()
    assert settings.location_data_path == Path("config/location.json")
