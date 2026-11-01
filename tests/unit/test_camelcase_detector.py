"""Unit: sweep key detector (spec 005 FR-011 / SC-001 canary).

Values — including strings with underscores — never violate; only keys do.
"""

import pytest

from tests.contract._camelcase import has_snake_case_keys


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"firstName": "Ana"}, False),
        ({"name_parts": 1}, True),
        ({"user": {"tokenType": "bearer"}, "items": [{"createdAt": 1}]}, False),
        ({"user": {"token_type": "bearer"}}, True),
        ({"items": [{"items": [{"deep": {"nestedOk": 1}}]}]}, False),
        ({"items": [{"items": [{"deep_not_ok": 1}]}]}, True),
        # False positives guard: underscore VALUES pass
        ({"email": "ana_silva@example.com", "cpf": "123_456"}, False),
        ({"nested": [{"note": "first_name_tourist"}]}, False),
        ([{"a": 1}, {"b_": 2}], True),
        ("plain string", False),
        ([1, 2, 3], False),
    ],
)
def test_has_snake_case_keys(payload: object, expected: bool) -> None:
    assert has_snake_case_keys(payload) is expected


def test_canary_planted_snake_key_is_detected() -> None:
    """SC-001: a planted snake_case key makes the sweep red (not vacuous)."""
    payload = {"accessToken": "x", "refresh_token": "planted"}
    assert has_snake_case_keys(payload) is True
