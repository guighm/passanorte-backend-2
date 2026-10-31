"""Aplicação única do monolito modular PassaNorte.

Monta os routers dos 10 módulos de domínio sob ``/api/v1`` (ver
``core.routers``) e expõe ``GET /health`` na raiz — 200 saudável ou 503
degradado com o estado do banco (clarificação Q1). Scripts ``passanorte-back``
e ``dev`` continuam apontando para este app.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from passanorte_back.core.db import engine, ping_database
from passanorte_back.core.routers import register_routers

app = FastAPI(title="Passanorte API", version="0.1.0")
register_routers(app)


@app.get("/health")
def health() -> JSONResponse:
    """Sonda de saúde: 200 {ok, ok} ou 503 {degraded, unavailable}."""
    if ping_database(engine):
        return JSONResponse(status_code=200, content={"status": "ok", "database": "ok"})
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "database": "unavailable"},
    )


def main() -> None:
    uvicorn.run("passanorte_back.main:app", host="0.0.0.0", port=8000, reload=True)
