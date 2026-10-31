"""Database access (SQLAlchemy 2.0) and database health check.

Single convergence point across engines: everything that varies by driver
(pool, engine options) lives here — the rest of the application only uses
``sessionfactory``, ``get_session`` and ``ping_database``. The engine is
inferred from ``settings.database_url`` (FR-014; RNF17) — no database
decision in domain code.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from passanorte_back.core.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base of the domain tables (each module owns its models
    in its repositories layer; no table is shared across domains)."""


# Short fixed timeout for the /health ping (SC-002: response < 1 s).
PING_TIMEOUT_S = 2.0


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create the synchronous engine from the configured URL.

    In-memory SQLite uses ``StaticPool`` (a single shared connection
    — required for ``:memory:`` to work across connections); other
    engines use SQLAlchemy defaults with ``pool_pre_ping``.
    """
    url = make_url(settings.database_url)
    is_memory_sqlite = url.drivername.startswith("sqlite") and (
        not url.database or url.database == ":memory:"
    )
    if is_memory_sqlite:
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(settings.database_url, pool_pre_ping=True)


def ping_database(engine: Engine) -> bool:
    """Run ``SELECT 1``; ``False`` when the database is unavailable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any failure means degraded in /health
        return False
    return True


def get_sessionfactory(engine: Engine) -> sessionmaker[Session]:
    """Create the session factory bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(sessionfactory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional context manager: commit on success, rollback on error."""
    session = sessionfactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


settings = get_settings()
engine = create_engine_from_settings(settings)
sessionfactory = get_sessionfactory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: transactional session per request."""
    yield from session_scope(sessionfactory)
