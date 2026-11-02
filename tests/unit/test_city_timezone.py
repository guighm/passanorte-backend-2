"""Unit: ``Settings.resolved_city_timezone`` (feature 007 — research R5).

Pure configuration data (RNF06): the city timezone lives in
``config/location.json`` with a ``CITY_TIMEZONE`` env override, validated
with ``zoneinfo``; missing/empty/unknown keys are structured errors that
name the problem. Tests isolate the location file via ``LOCATION_DATA_PATH``
(temp JSON fixtures) — the repository's own ``config/location.json`` is NOT
a dependency.
"""

import json
from pathlib import Path

import pytest

from passanorte_back.core.config import LocationDataError, get_settings


def _settings_with_location(tmp_path: Path, content: dict) -> object:
    """Fresh ``Settings`` reading a temp location file (env override set)."""
    location_file = tmp_path / "location.json"
    location_file.write_text(json.dumps(content), encoding="utf-8")
    return get_settings().model_copy(
        update={"location_data_path": location_file, "city_timezone": None}
    )


def test_resolved_city_timezone_from_location_file(tmp_path: Path) -> None:
    settings = _settings_with_location(tmp_path, {"city_timezone": "America/Sao_Paulo"})
    assert settings.resolved_city_timezone() == "America/Sao_Paulo"


def test_resolved_city_timezone_env_override_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CITY_TIMEZONE", "Europe/Lisbon")
    settings = _settings_with_location(tmp_path, {"city_timezone": "America/Sao_Paulo"})
    settings = settings.model_copy(update={"city_timezone": "Europe/Lisbon"})
    assert settings.resolved_city_timezone() == "Europe/Lisbon"


def test_missing_city_timezone_key_is_location_data_error(tmp_path: Path) -> None:
    settings = _settings_with_location(tmp_path, {"city": "X"})
    with pytest.raises(LocationDataError, match="city_timezone"):
        settings.resolved_city_timezone()


def test_empty_city_timezone_is_location_data_error(tmp_path: Path) -> None:
    settings = _settings_with_location(tmp_path, {"city_timezone": "   "})
    with pytest.raises(LocationDataError, match="city_timezone"):
        settings.resolved_city_timezone()


def test_unknown_city_timezone_is_location_data_error(tmp_path: Path) -> None:
    settings = _settings_with_location(tmp_path, {"city_timezone": "Mars/Olympus_Mons"})
    with pytest.raises(LocationDataError, match="city_timezone"):
        settings.resolved_city_timezone()
