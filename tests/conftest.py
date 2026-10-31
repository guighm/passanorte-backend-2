"""Configuração global de testes: ambiente fixo e sintético.

Fixa DATABASE_URL (SQLite em memória) e JWT_SECRET sintético — jamais um
segredo real (Quality Gate: nenhum dado sensível em teste, FR-011).
Cada teste que precisa de outro perfil sobrescreve via monkeypatch.
"""

import os

import pytest

TEST_DATABASE_URL = "sqlite:///:memory:"
TEST_JWT_SECRET = "test-only-synthetic-secret-not-real"

# Essenciais também no nível do módulo (tempo de coleta): módulos de teste
# que importam ``passanorte_back.main`` (e, indiretamente, ``core.db``, que
# constrói Settings) rodam antes de qualquer fixture.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def _test_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiente essencial sintético para todos os testes (autouse)."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    # Isola os testes de qualquer .env presente no checkout.
    monkeypatch.delenv("JWT_TTL", raising=False)
    monkeypatch.delenv("GPS_TOLERANCE_RADIUS_M", raising=False)
    monkeypatch.delenv("CITY_NAME", raising=False)
    monkeypatch.delenv("ENABLED_LANGUAGES", raising=False)
    monkeypatch.delenv("LOCATION_DATA_PATH", raising=False)
    assert os.environ["DATABASE_URL"] == TEST_DATABASE_URL
