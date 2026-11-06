"""Unit: localization picker and portability of category labels (feature
016 — T036, FR-019, SC-007).

Closes analyze findings F2/F3: the localized-text selection is exercised
on its own (exact match, language-base fallback, Portuguese canonical)
and the category labels follow the CONFIGURED location file — proving the
pipeline has no language/city/category hardcode (RNF06/SC-007 design
guarantee, now backed by a test).
"""

import json

from passanorte_back.modules.chatbot.services.chat import UNAVAILABLE_TEXT, _localize
from passanorte_back.modules.chatbot.services.retrieval import category_label_tokens


def test_exact_language_match() -> None:
    assert _localize(UNAVAILABLE_TEXT, "pt-BR") == UNAVAILABLE_TEXT["pt-BR"]


def test_language_base_fallback() -> None:
    """'pt-PT' has no exact entry → falls back to the pt language base."""
    assert _localize(UNAVAILABLE_TEXT, "pt-PT") == UNAVAILABLE_TEXT["pt-BR"]


def test_portuguese_is_canonical_fallback() -> None:
    """Languages outside the configured set still get a sensible answer."""
    assert _localize(UNAVAILABLE_TEXT, "zz-ZZ") == UNAVAILABLE_TEXT["pt-BR"]


def test_category_labels_come_from_configuration(monkeypatch, tmp_path) -> None:
    """SC-007: labels are resolved from the location data file — a
    different configuration yields different label tokens (RNF06)."""
    location = {
        "city": "Outra Cidade",
        "city_timezone": "America/Sao_Paulo",
        "languages": ["pt-BR"],
        "interest_categories": [
            {"key": "cascata", "label": "Água e Cachoeira"},
            {"key": "arlivre", "label": "Ar Livre"},
        ],
    }
    path = tmp_path / "location.json"
    path.write_text(json.dumps(location), encoding="utf-8")
    monkeypatch.setenv("LOCATION_DATA_PATH", str(path))

    from passanorte_back.core.config import get_settings

    get_settings.cache_clear()
    try:
        tokens = category_label_tokens(["cascata"])
        # Tokens of the configured label — accents stripped, stopwords kept
        # (they are part of labels, not the query).
        assert {"agua", "cachoeira"} <= tokens
        assert "arlivre" not in tokens
    finally:
        get_settings.cache_clear()
