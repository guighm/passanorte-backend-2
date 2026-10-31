"""Central router registry for the domain modules (research R6).

One ``APIRouter`` per module, prefix ``/api/v1/<name-with-hyphens>``
(``_`` → ``-``), names taken from the canonical ``DOMAIN_MODULES`` list
(``core/modules.py``). Registration is stable-ordered and unique: adding a
module there is enough to mount it in the app (``register_routers`` in
``main.py``). In the foundation the routers are empty — no business
endpoint (FR-006/007); future feature contracts MUST reuse these prefixes.

``/health`` and the documentation (``/docs``, ``/openapi.json``) live at the
root, outside ``/api/v1`` (clarification Q4).
"""

from typing import Final

from fastapi import APIRouter, FastAPI

from passanorte_back.core.modules import DOMAIN_MODULES

API_V1_PREFIX: Final = "/api/v1"


def module_prefix(module: str) -> str:
    """Module HTTP prefix: canonical package name with ``_`` → ``-``."""
    return f"{API_V1_PREFIX}/{module.replace('_', '-')}"


MODULE_ROUTERS: Final[dict[str, APIRouter]] = {
    name: APIRouter(prefix=module_prefix(name)) for name in DOMAIN_MODULES
}


def register_routers(app: FastAPI) -> None:
    """Mount every domain router in the app (include_router)."""
    for router in MODULE_ROUTERS.values():
        app.include_router(router)
