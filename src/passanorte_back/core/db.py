"""Acesso a banco (SQLAlchemy 2.0) e verificação de saúde do banco.

Única convergência entre motores: tudo o que varia por driver (pool,
opções de engine) fica aqui — o resto da aplicação usa apenas
``sessionfactory``, ``get_session`` e ``ping_database``. O motor é deduzido
da ``settings.database_url`` (FR-014; RNF17) — nenhuma decisão de banco no
código de domínio.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from passanorte_back.core.config import Settings, get_settings

# Timeout fixo curto para o ping do /health (SC-002: resposta < 1 s).
PING_TIMEOUT_S = 2.0


def create_engine_from_settings(settings: Settings) -> Engine:
    """Cria a engine síncrona a partir da URL configurada.

    SQLite em memória usa ``StaticPool`` (uma única conexão compartilhada
    — obrigatório para ``:memory:`` funcionar entre conexões); demais
    motores usam os defaults do SQLAlchemy com ``pool_pre_ping``.
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
    """Executa ``SELECT 1``; ``False`` se o banco estiver indisponível."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — qualquer falha = degradado no /health
        return False
    return True


def get_sessionfactory(engine: Engine) -> sessionmaker[Session]:
    """Cria a session factory vinculada à engine dada."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(sessionfactory: sessionmaker[Session]) -> Iterator[Session]:
    """Context manager transacional: commit em sucesso, rollback em erro."""
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
    """Dependência FastAPI: sessão transacional por request."""
    yield from session_scope(sessionfactory)
