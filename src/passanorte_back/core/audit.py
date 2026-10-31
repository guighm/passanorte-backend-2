"""Serviço de auditoria estruturado, log-only (RNF19; clarificação Q3).

``record_action`` emite exatamente 1 linha JSON por ação no logger dedicado
``passanorte.audit`` (stdout), com os 5 campos obrigatórios — ``timestamp``
(ISO-8601 UTC), ``actor``, ``action``, ``target``, ``result`` — e ``detail``
opcional (FR-017). Falha de emissão levanta ``AuditError`` ao chamador
(FR-018).

Qualquer módulo consome via import de ``core`` (compartilhável sem violar
fronteira). Persistência em tabela, quando necessária, substitui/complementa
o sink — a interface de ``record_action`` não muda.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Final, Literal

AuditResult = Literal["success", "failure"]

AUDIT_LOGGER_NAME: Final = "passanorte.audit"
AUDIT_LEVEL: Final[int] = logging.INFO


class AuditError(RuntimeError):
    """Falha do sink de auditoria (FR-018)."""


def _configure_logger() -> logging.Logger:
    """Logger dedicado com handler JSON para stdout (configurado uma vez)."""
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(AUDIT_LEVEL)
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = True  # capturável em testes e coletável por log central
    return logger


logger = _configure_logger()


def _emit(message: str) -> None:
    """Sink da auditoria — trocável para persistência futura."""
    logger.log(AUDIT_LEVEL, message)


def record_action(
    actor: str,
    action: str,
    target: str,
    result: AuditResult,
    *,
    detail: dict[str, object] | str | None = None,
) -> None:
    """Registra 1 ação de auditoria com os campos mínimos (FR-017).

    Levanta ``AuditError`` se a emissão falhar (FR-018).
    """
    record: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": actor,
        "action": action,
        "target": target,
        "result": result,
    }
    if detail is not None:
        record["detail"] = detail
    try:
        _emit(json.dumps(record, ensure_ascii=False))
    except Exception as error:
        raise AuditError(f"Sink de auditoria falhou: {error}") from error
