"""Smoke: serviço de auditoria (FR-017/FR-018, SC-007; data-model AuditRecord).

``record_action`` emite exatamente 1 registro JSON por ação com os 5 campos
obrigatórios e ``detail`` opcional; ``result`` distingue
``success``/``failure``; falha do sink levanta ``AuditError``.
"""

import json
import logging

import pytest

from passanorte_back.core.audit import AUDIT_LOGGER_NAME, AuditError, record_action


@pytest.fixture()
def audit_records() -> list[dict[str, object]]:
    """Captura os JSONs emitidos pelo logger de auditoria em tempo real."""
    records: list[dict[str, object]] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.name == AUDIT_LOGGER_NAME:
                records.append(json.loads(record.getMessage()))

    capture = _Capture()
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.addHandler(capture)
    try:
        yield records
    finally:
        audit_logger.removeHandler(capture)


def test_record_action_emits_exactly_one_json_record_with_five_fields(
    audit_records: list[dict[str, object]],
) -> None:
    record_action(actor="admin-1", action="create_point", target="point:4", result="success")

    assert len(audit_records) == 1
    record = audit_records[0]
    assert record["timestamp"]  # ISO-8601 UTC
    assert record["actor"] == "admin-1"
    assert record["action"] == "create_point"
    assert record["target"] == "point:4"
    assert record["result"] == "success"


def test_record_action_includes_optional_detail(
    audit_records: list[dict[str, object]],
) -> None:
    record_action(
        actor="func-9",
        action="remove_event",
        target="event:12",
        result="failure",
        detail={"reason": "evento encerrado"},
    )

    record = audit_records[0]
    assert record["result"] == "failure"
    assert record["detail"] == {"reason": "evento encerrado"}


def test_timestamp_is_iso8601_utc(audit_records: list[dict[str, object]]) -> None:
    from datetime import datetime

    record_action(actor="a", action="act", target="t", result="success")
    timestamp = audit_records[0]["timestamp"]
    assert isinstance(timestamp, str)
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0


def test_sink_failure_raises_audit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from passanorte_back.core import audit

    def broken_emit(*args: object, **kwargs: object) -> None:
        raise OSError("sink indisponível")

    monkeypatch.setattr(audit, "_emit", broken_emit)
    with pytest.raises(AuditError) as exc:
        record_action(actor="a", action="act", target="t", result="success")
    assert "sink indisponível" in str(exc.value)


def test_no_detail_key_when_not_provided(
    audit_records: list[dict[str, object]],
) -> None:
    record_action(actor="a", action="act", target="t", result="success")
    assert "detail" not in audit_records[0]
