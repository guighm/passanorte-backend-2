"""Application configuration (pydantic-settings).

Two REQUIRED values with no default (FR-010/FR-012): ``database_url`` and
``jwt_secret``. The absence of either one interrupts initialization with a
message naming the field (FR-012). Secrets live exclusively in environment
variables / ``.env`` — never in code (FR-011).

The database profile (PostgreSQL production / SQLite tests) is chosen only
by the URL in ``database_url`` (FR-014; RNF17) — no engine decision in
source code.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocationDataError(RuntimeError):
    """Location data missing, invalid or lacking the expected keys."""


class Settings(BaseSettings):
    """Configuration values loaded from the environment at startup.

    Required (no default): ``database_url``, ``jwt_secret``. With default:
    ``jwt_ttl`` (3600 s), ``jwt_refresh_ttl`` (604800 s), ``gps_tolerance_radius_m``
    (100.0), ``city_name``
    and ``languages`` (from the location file), ``location_data_path``
    (``config/location.json``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    jwt_secret: str
    jwt_ttl: int = 3600
    jwt_refresh_ttl: int = 604800
    gps_tolerance_radius_m: float = 100.0
    city_name: str | None = None
    languages: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("languages", "ENABLED_LANGUAGES"),
    )
    location_data_path: Path = Path("config/location.json")

    @field_validator("database_url", "jwt_secret")
    @classmethod
    def _reject_empty(cls, value: str, info: ValidationInfo) -> str:
        field = getattr(info, "field_name", "field")
        if not value or not value.strip():
            raise ValueError(f"'{field}' cannot be empty or whitespace only")
        return value

    @field_validator("jwt_ttl", "jwt_refresh_ttl", "gps_tolerance_radius_m")
    @classmethod
    def _reject_non_positive(cls, value: int | float, info: ValidationInfo) -> int | float:
        field = getattr(info, "field_name", "field")
        if value <= 0:
            raise ValueError(f"'{field}' must be greater than zero (received: {value})")
        return value

    @model_validator(mode="after")
    def _reject_explicitly_empty_languages(self) -> "Settings":
        if self.languages is not None and not self.languages:
            raise ValueError(
                "'languages' cannot be an explicitly empty list (ENABLED_LANGUAGES=[])"
            )
        return self

    def _read_location_data(self) -> dict[str, Any]:
        """Read the location file (data, never code — RNF06)."""
        path = self.location_data_path
        if not path.is_file():
            raise LocationDataError(
                f"Location data file not found: '{path}' —"
                " provide a file with 'city' and 'languages' keys."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
            raise LocationDataError(f"Invalid location data file: '{path}' ({error})") from error
        if not isinstance(data, dict):
            raise LocationDataError(
                f"Invalid location data file: '{path}' must contain a JSON object."
            )
        return data

    def resolved_city(self) -> str:
        """Effective city: environment override > location file."""
        if self.city_name is not None:
            return self.city_name
        data = self._read_location_data()
        city = data.get("city")
        if not isinstance(city, str) or not city.strip():
            raise LocationDataError(
                f"Key 'city' missing or empty in location data file '{self.location_data_path}'."
            )
        return city

    def resolved_languages(self) -> list[str]:
        """Effective languages: environment override > location file."""
        if self.languages is not None:
            return self.languages
        data = self._read_location_data()
        languages = data.get("languages")
        if (
            not isinstance(languages, list)
            or not all(isinstance(item, str) and item.strip() for item in languages)
            or not languages
        ):
            raise LocationDataError(
                f"Key 'languages' must be a non-empty list in '{self.location_data_path}'."
            )
        return languages


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton ``Settings`` instance (loaded on first use)."""
    return Settings()
