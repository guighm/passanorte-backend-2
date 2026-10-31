"""Structured, log-only audit service (RNF19; clarification Q3).

``record_action`` emits exactly 1 JSON line per action on the dedicated
``passanorte.audit`` logger (stdout), with the 5 mandatory fields —
``timestamp`` (ISO-8601 UTC), ``actor``, ``action``, ``target``, ``result``
— and optional ``detail`` (FR-017). Emission failure raises ``AuditError``
to the caller (FR-018).

Every module consumes it via a ``core`` import (shareable without violating
boundaries). Table persistence, when needed, replaces/complements the sink
— the ``record_action`` interface does not change.
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
    """Audit sink failure (FR-018)."""


def _configure_logger() -> logging.Logger:
    """Dedicated logger with a JSON handler for stdout (configured once)."""
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(AUDIT_LEVEL)
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = True  # capture-able in tests and collectable by a central log
    return logger


logger = _configure_logger()


def _emit(message: str) -> None:
    """Audit sink — swappable for future persistence."""
    logger.log(AUDIT_LEVEL, message)


def record_action(
    actor: str,
    action: str,
    target: str,
    result: AuditResult,
    *,
    detail: dict[str, object] | str | None = None,
) -> None:
    """Record 1 audit action with the mandatory fields (FR-017).

    Raises ``AuditError`` when emission fails (FR-018).
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
        raise AuditError(f"Audit sink failed: {error}") from error
