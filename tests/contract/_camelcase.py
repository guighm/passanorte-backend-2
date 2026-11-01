"""Pure-function key detector for the camelCase contract sweep (spec 005).

Test infrastructure shared by ``tests/unit/test_camelcase_detector.py`` and
``tests/contract/test_camelcase_contract.py``. Values are never inspected —
only JSON keys follow the convention (spec 005 assumptions); a key violates
exactly when it contains an underscore (clarification Q2 — deterministic,
no acronym whitelist).
"""

from typing import Any


def has_snake_case_keys(value: Any) -> bool:
    """True when any JSON key at any nesting level contains an underscore."""
    if isinstance(value, dict):
        return any("_" in str(key) for key in value) or any(
            has_snake_case_keys(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(has_snake_case_keys(item) for item in value)
    return False
