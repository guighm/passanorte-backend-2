"""Registro central de routers dos módulos de domínio (research R6).

Um ``APIRouter`` por módulo, prefixo ``/api/v1/<nome-com-hifens>`` (``_`` →
``-``). O registro é ordem-estável e único: incluir um módulo novo aqui é o
suficiente para montá-lo no app (``register_routers`` em ``main.py``). Na
fundaçăo os routers estão vazios — nenhum endpoint de negócio (FR-006/007);
contratos de negócio das features futuras reutilizam estes prefixos
obrigatoriamente.

``/health`` e a documentação (``/docs``, ``/openapi.json``) vivem na raiz,
fora de ``/api/v1`` (clarificação Q4).
"""

from typing import Final

from fastapi import APIRouter, FastAPI

from passanorte_back.core.modules import DOMAIN_MODULES

API_V1_PREFIX: Final = "/api/v1"


def module_prefix(module: str) -> str:
    """Prefixo HTTP do módulo: nome do pacote com ``_`` → ``-``."""
    return f"{API_V1_PREFIX}/{module.replace('_', '-')}"


MODULE_ROUTERS: Final[dict[str, APIRouter]] = {
    name: APIRouter(prefix=module_prefix(name)) for name in DOMAIN_MODULES
}


def register_routers(app: FastAPI) -> None:
    """Monta todos os routers de domínio no app (include_router)."""
    for router in MODULE_ROUTERS.values():
        app.include_router(router)
