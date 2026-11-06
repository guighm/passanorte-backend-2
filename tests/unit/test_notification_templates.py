"""Unit: notification text composition (feature 015 — research R5, Q2).

Pure functions: per-type templates keyed by item type, description capped,
unknown type rejected. The template map is the single i18n seam (RNF16) —
exact strings pinned so future localization changes are deliberate.
"""

import pytest
from fastapi import HTTPException

from passanorte_back.modules.notifications.services.emission import (
    compose_description,
    compose_title,
    validate_item_type,
)

LONG = "x" * 500


def test_title_per_item_type() -> None:
    assert compose_title("event", "Festival de Peixes") == "Novo evento: Festival de Peixes"
    assert compose_title("spot", "Cachoeira Édem") == "Novo ponto turístico: Cachoeira Édem"
    assert compose_title("route", "Três Cachoeiras") == "Nova rota turística: Três Cachoeiras"


def test_description_is_capped() -> None:
    assert compose_description("event", "x" * 10) == "x" * 10
    assert len(compose_description("spot", LONG)) == 200


def test_unknown_item_type_is_rejected() -> None:
    for compose in (compose_title, compose_description):
        with pytest.raises(HTTPException) as error:
            compose("prize", "X")
        assert error.value.status_code == 422


def test_validate_item_type_accepts_only_catalog() -> None:
    assert validate_item_type("event") == "event"
    assert validate_item_type("spot") == "spot"
    assert validate_item_type("route") == "route"
    with pytest.raises(HTTPException) as error:
        validate_item_type("gift")
    assert error.value.status_code == 422
