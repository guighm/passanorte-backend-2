"""Configuração da aplicação (pydantic-settings).

Dois valores ESSenciais sem default (FR-010/FR-012): ``database_url`` e
``jwt_secret``. A ausência de qualquer um deles interrompe a inicialização
com mensagem nomeando o campo (FR-012). Segredos vivem exclusivamente em
variáveis de ambiente / ``.env`` — nunca no código (FR-011).

O perfil do banco (PostgreSQL produção / SQLite testes) é escolhido apenas
pela URL em ``database_url`` (FR-014; RNF17) — nenhuma decisão de motor no
código fonte.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocationDataError(RuntimeError):
    """Dados de localidade ausentes, inválidos ou sem as chaves esperadas."""


class Settings(BaseSettings):
    """Valores de configuração carregados do ambiente no startup.

    Essenciais (sem default): ``database_url``, ``jwt_secret``. Com default:
    ``jwt_ttl`` (3600 s), ``gps_tolerance_radius_m`` (100.0), ``city_name`` e
    ``languages`` (do arquivo de localidade), ``location_data_path``
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
        field = getattr(info, "field_name", "campo")
        if not value or not value.strip():
            raise ValueError(f"'{field}' não pode ser vazio ou só espaços")
        return value

    @field_validator("jwt_ttl", "gps_tolerance_radius_m")
    @classmethod
    def _reject_non_positive(cls, value: int | float, info: ValidationInfo) -> int | float:
        field = getattr(info, "field_name", "campo")
        if value <= 0:
            raise ValueError(f"'{field}' deve ser maior que zero (recebido: {value})")
        return value

    @model_validator(mode="after")
    def _reject_explicitly_empty_languages(self) -> "Settings":
        if self.languages is not None and not self.languages:
            raise ValueError(
                "'languages' não pode ser uma lista explicitamente vazia (ENABLED_LANGUAGES=[])"
            )
        return self

    def _read_location_data(self) -> dict[str, Any]:
        """Lê o arquivo de localidade (dados, nunca código — RNF06)."""
        path = self.location_data_path
        if not path.is_file():
            raise LocationDataError(
                f"Arquivo de localidade não encontrado: '{path}' —"
                " forneça um arquivo com as chaves 'city' e 'languages'."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
            raise LocationDataError(
                f"Arquivo de localidade inválido: '{path}' ({error})"
            ) from error
        if not isinstance(data, dict):
            raise LocationDataError(
                f"Arquivo de localidade inválido: '{path}' deve conter um objeto JSON."
            )
        return data

    def resolved_city(self) -> str:
        """Cidade efetiva: override de ambiente > arquivo de localidade."""
        if self.city_name is not None:
            return self.city_name
        data = self._read_location_data()
        city = data.get("city")
        if not isinstance(city, str) or not city.strip():
            raise LocationDataError(
                f"Chave 'city' ausente ou vazia no arquivo de "
                f"localidade '{self.location_data_path}'."
            )
        return city

    def resolved_languages(self) -> list[str]:
        """Idiomas efetivos: override de ambiente > arquivo de localidade."""
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
                f"Chave 'languages' precisa ser uma lista não vazia em '{self.location_data_path}'."
            )
        return languages


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a instância única de ``Settings`` (carregada no primeiro uso)."""
    return Settings()
