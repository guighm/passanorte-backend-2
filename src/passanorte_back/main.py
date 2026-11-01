"""Single application of the PassaNorte modular monolith.

Mounts the routers of the 10 domain modules under ``/api/v1`` (see
``core.routers``) and exposes ``GET /health`` at the root — 200 healthy or
503 degraded with the database state (clarification Q1). The
``passanorte-back`` and ``dev`` scripts keep pointing to this app.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from passanorte_back.core.db import engine, ping_database
from passanorte_back.core.error_handlers import register_error_handlers
from passanorte_back.core.routers import register_routers
from passanorte_back.core.schemas import ApiError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifespan (plan.md "ciclo de vida"): dispose the DB engine on shutdown."""
    yield
    engine.dispose()


app = FastAPI(title="Passanorte API", version="0.1.0", lifespan=lifespan)
register_routers(app)
register_error_handlers(app)


def custom_openapi() -> dict[str, Any]:
    """OpenAPI with the unified error DTO registered (spec 005 FR-005/Q1).

    Handlers return ``ApiError`` payloads from exception paths, which plain
    route inspection never sees — so the unified error schema (and its key
    details item) is merged into the components map explicitly.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes
    )
    error_schema = TypeAdapter(ApiError).json_schema(
        ref_template="#/components/schemas/{model}",
        mode="validation",
    )
    definitions: dict[str, Any] = error_schema.pop("$defs", {})
    schema.setdefault("components", {}).setdefault("schemas", {})
    schema["components"]["schemas"].update(definitions)
    schema["components"]["schemas"]["ApiError"] = error_schema
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.get("/health")
def health() -> JSONResponse:
    """Health probe: 200 {ok, ok} or 503 {degraded, unavailable}."""
    if ping_database(engine):
        return JSONResponse(status_code=200, content={"status": "ok", "database": "ok"})
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "database": "unavailable"},
    )


def main() -> None:
    uvicorn.run("passanorte_back.main:app", host="0.0.0.0", port=8000, reload=True)
