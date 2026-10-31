"""Single application of the PassaNorte modular monolith.

Mounts the routers of the 10 domain modules under ``/api/v1`` (see
``core.routers``) and exposes ``GET /health`` at the root — 200 healthy or
503 degraded with the database state (clarification Q1). The
``passanorte-back`` and ``dev`` scripts keep pointing to this app.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from passanorte_back.core.db import engine, ping_database
from passanorte_back.core.routers import register_routers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifespan (plan.md "ciclo de vida"): dispose the DB engine on shutdown."""
    yield
    engine.dispose()


app = FastAPI(title="Passanorte API", version="0.1.0", lifespan=lifespan)
register_routers(app)


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
