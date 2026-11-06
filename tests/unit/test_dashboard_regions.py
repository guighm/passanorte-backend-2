"""Unit: heat-map region resolution from location data (research R5, FR-005).

Regions are pure data (RNF06): each named region lists the tourist-spot
names it groups. The resolver never touches the database — it parses the
optional ``regions`` block, computes centroid coordinates, skips unknown
spot names with a structured log and reports absence of the block.
"""

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from passanorte_back.core.config import Settings
from passanorte_back.modules.dashboard.services.metrics import (
    RegionDefinition,
    resolve_regions,
)

COORDS = {
    "Cachoeira Édem": (-22.40, -45.00),
    "Cachoeira do Serra": (-22.50, -45.10),
    "Mirante": (-22.30, -44.95),
}


def _write_location(tmp_path: Path, regions: list[dict] | None) -> Settings:
    data: dict = {
        "city": "Passa Quatro",
        "city_timezone": "America/Sao_Paulo",
        "languages": ["pt-BR"],
        "interest_categories": [{"key": "nature", "label": "Natureza"}],
    }
    if regions is not None:
        data["regions"] = regions
    location = tmp_path / "location.json"
    location.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return Settings.model_construct(
        database_url="sqlite:///:memory:",
        jwt_secret="unused",
        sensitive_data_key="unused",
        location_data_path=location,
    )


REGIONS = [
    {
        "key": "waterfalls",
        "label": "Cachoeiras",
        "spots": ["Cachoeira Édem", "Cachoeira do Serra", "Desconhecida"],
    },
    {"key": "core", "label": "Centro", "spots": ["Mirante"]},
]


def test_regions_resolve_centroid_and_skip_unknown_spots(tmp_path: Path) -> None:
    settings = _write_location(
        tmp_path,
        [
            {
                "key": "waterfalls",
                "label": "Cachoeiras",
                "spots": ["Cachoeira Édem", "Cachoeira do Serra", "Desconhecida"],
            }
        ],
    )
    resolved = resolve_regions(settings, COORDS)
    assert [(r.key, r.label) for r in resolved] == [("waterfalls", "Cachoeiras")]
    falls = resolved[0]
    assert isinstance(falls, RegionDefinition)
    # Centroid over the two KNOWN spots only (unknown name skipped).
    assert falls.latitude == pytest.approx((-22.40 - 22.50) / 2)
    assert falls.longitude == pytest.approx((-45.00 - 45.10) / 2)
    assert falls.spot_names == ("Cachoeira Édem", "Cachoeira do Serra")


def test_regions_block_absent_resolution_is_rejected(tmp_path: Path) -> None:
    """FR-005: no ``regions`` in location data → region mode is 422."""
    settings = _write_location(tmp_path, None)
    with pytest.raises(HTTPException) as error:
        resolve_regions(settings, COORDS)
    assert error.value.status_code == 422


def test_duplicate_region_keys_are_rejected(tmp_path: Path) -> None:
    settings = _write_location(
        tmp_path,
        [
            {"key": "core", "label": "Centro", "spots": ["Mirante"]},
            {"key": "core", "label": "Centro 2", "spots": ["Mirante"]},
        ],
    )
    with pytest.raises(HTTPException) as error:
        resolve_regions(settings, COORDS)
    assert error.value.status_code == 422


def test_region_with_no_known_spot_still_resolves(tmp_path: Path) -> None:
    """A region whose spots are all unknown resolves (empty group) — the
    aggregator then contributes weight zero."""
    settings = _write_location(tmp_path, [{"key": "ghost", "label": "Fantasma", "spots": ["Nada"]}])
    resolved = resolve_regions(settings, COORDS)
    assert resolved[0].latitude is None


def test_malformed_region_entries_are_rejected(tmp_path: Path) -> None:
    settings = _write_location(tmp_path, ["not-a-dict"])
    with pytest.raises(HTTPException) as error:
        resolve_regions(settings, COORDS)
    assert error.value.status_code == 422
