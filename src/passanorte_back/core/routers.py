"""Central router registry for the domain modules (research R6).

One ``APIRouter`` per module, prefix ``/api/v1/<name-with-hyphens>``
(``_`` → ``-``), names taken from the canonical ``DOMAIN_MODULES`` list
(``core/modules.py``) and tagged with the central registry tag
(``core/tags.py``, feature 006 FR-003) at this single creation point —
module route files never write a tag string. Registration is stable-ordered
and unique: adding a module there is enough to mount it in the app
(``register_routers`` in ``main.py``). In the foundation the routers are
empty — no business endpoint (FR-006/007); future feature contracts MUST
reuse these prefixes.

``/health`` and the documentation (``/docs``, ``/openapi.json``) live at the
root, outside ``/api/v1`` (clarification Q4).
"""

from importlib import import_module
from typing import Final

from fastapi import APIRouter, FastAPI

from passanorte_back.core.modules import DOMAIN_MODULES
from passanorte_back.core.tags import module_tag

API_V1_PREFIX: Final = "/api/v1"


def module_prefix(module: str) -> str:
    """Module HTTP prefix: canonical package name with ``_`` → ``-``."""
    return f"{API_V1_PREFIX}/{module.replace('_', '-')}"


MODULE_ROUTERS: Final[dict[str, APIRouter]] = {
    name: APIRouter(prefix=module_prefix(name), tags=[module_tag(name)])
    for name in DOMAIN_MODULES
}


def register_routers(app: FastAPI) -> None:
    """Mount every domain router in the app (include_router).

    Each module's ``routes`` package decorates its canonical router at
    import time (feature-driven; foundation routers stay empty without a
    routes module). The import happens here — the same include_router
    path used in production and by test probes.
    """
    for name, router in MODULE_ROUTERS.items():
        import_module(f"passanorte_back.modules.{name}.routes")
        app.include_router(router)
