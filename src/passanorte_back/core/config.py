"""Application configuration (pydantic-settings).

Three REQUIRED values with no default (FR-010/FR-012): ``database_url``,
``jwt_secret`` and ``sensitive_data_key`` (RNF08). The absence of any one
interrupts initialization with a message naming the field (FR-012). Secrets
live exclusively in environment variables / ``.env`` — never in code
(FR-011).

The database profile (PostgreSQL production / SQLite tests) is chosen only
by the URL in ``database_url`` (FR-014; RNF17) — no engine decision in
source code.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocationDataError(RuntimeError):
    """Location data missing, invalid or lacking the expected keys."""


class Settings(BaseSettings):
    """Configuration values loaded from the environment at startup.

    Required (no default): ``database_url``, ``jwt_secret``,
    ``sensitive_data_key``. With default: ``jwt_ttl`` (3600 s),
    ``jwt_refresh_ttl`` (604800 s), ``gps_tolerance_radius_m``
    (100.0), ``city_name``, ``city_timezone`` and ``languages`` (from the
    location file), ``location_data_path`` (``config/location.json``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    jwt_secret: str
    sensitive_data_key: str
    jwt_ttl: int = 3600
    jwt_refresh_ttl: int = 604800
    gps_tolerance_radius_m: float = 100.0
    # Discovery ranking policy (feature 013 — configuration, never code;
    # constitution VI). Weights must be positive and sum to exactly 1 —
    # validated at startup in ``_validate_discovery_weights``.
    discovery_w_proximity: float = 0.5
    discovery_w_interest: float = 0.35
    discovery_w_event: float = 0.15
    discovery_max_distance_km: float = 10.0
    discovery_event_window_days: int = 30
    discovery_event_boost_min: float = 0.25
    discovery_neutral_proximity: float = 0.5
    discovery_map_provider: str = "google_maps"
    city_name: str | None = None
    city_timezone: str | None = None
    languages: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("languages", "ENABLED_LANGUAGES"),
    )
    location_data_path: Path = Path("config/location.json")

    @field_validator("database_url", "jwt_secret", "sensitive_data_key")
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

    @field_validator(
        "discovery_max_distance_km",
        "discovery_event_window_days",
    )
    @classmethod
    def _reject_non_positive_discovery(
        cls, value: int | float, info: ValidationInfo
    ) -> int | float:
        field = getattr(info, "field_name", "field")
        if value <= 0:
            raise ValueError(f"'{field}' must be greater than zero (received: {value})")
        return value

    @field_validator("discovery_event_boost_min", "discovery_neutral_proximity")
    @classmethod
    def _reject_out_of_range_discovery_factor(cls, value: float, info: ValidationInfo) -> float:
        field = getattr(info, "field_name", "field")
        if not 0 <= value <= 1:
            raise ValueError(f"'{field}' must be between 0 and 1 inclusive (received: {value})")
        return value

    @field_validator("discovery_map_provider")
    @classmethod
    def _validate_map_provider(cls, value: str) -> str:
        if value not in ("google_maps", "osm"):
            raise ValueError("'discovery_map_provider' must be 'google_maps' or 'osm'")
        return value

    @model_validator(mode="after")
    def _validate_discovery_weights(self) -> "Settings":
        """Discovery weights: each > 0 and summing to exactly 1 (feature 013)."""
        weights = (
            self.discovery_w_proximity,
            self.discovery_w_interest,
            self.discovery_w_event,
        )
        for weight in weights:
            if weight <= 0:
                raise ValueError("discovery weights must each be greater than zero")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError(f"discovery weights must sum to 1 (received: {sum(weights)})")
        return self

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

    def resolved_interest_categories(self) -> list[dict[str, str]]:
        """Interest categories from the location file (data, not code — RNF06).

        Each item must carry a non-empty ``key`` (canonical English code
        identifier) and a non-empty ``label`` (user-facing text). Missing or
        invalid block → structured ``LocationDataError``.
        """
        data = self._read_location_data()
        categories = data.get("interest_categories")
        if not isinstance(categories, list) or not categories:
            raise LocationDataError(
                "Key 'interest_categories' must be a non-empty list of "
                f"{{'key', 'label'}} objects in '{self.location_data_path}'."
            )
        resolved: list[dict[str, str]] = []
        for item in categories:
            if not isinstance(item, dict):
                raise LocationDataError(
                    "Each entry of 'interest_categories' must be an object "
                    f"with 'key' and 'label' in '{self.location_data_path}'."
                )
            key = item.get("key")
            label = item.get("label")
            if (
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(label, str)
                or not label.strip()
            ):
                raise LocationDataError(
                    "Each entry of 'interest_categories' needs non-empty "
                    f"'key' and 'label' strings in '{self.location_data_path}'."
                )
            resolved.append({"key": key.strip(), "label": label.strip()})
        return resolved

    def resolved_city_timezone(self) -> str:
        """City timezone for dateless schedule times (feature 007, RNF06).

        Environment override > location file (same precedence as city/
        languages). The value must be a valid IANA timezone name — validated
        with ``zoneinfo`` so an invalid configuration fails at startup, not
        at the first read.
        """
        if self.city_timezone is not None:
            key = self.city_timezone.strip()
        else:
            key = str(self._read_location_data().get("city_timezone", "")).strip()
        if not key:
            raise LocationDataError(
                f"'city_timezone' missing or empty in the location data "
                f"('{self.location_data_path}' or CITY_TIMEZONE override)."
            )
        try:
            ZoneInfo(key)  # noqa: B018 — validation only
        except Exception as error:  # zoneinfo raises several exception types
            raise LocationDataError(
                f"'city_timezone' '{key}' is not a valid IANA timezone in the "
                f"location data ('{self.location_data_path}' or CITY_TIMEZONE override)."
            ) from error
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton ``Settings`` instance (loaded on first use)."""
    return Settings()
