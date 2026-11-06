"""Unit: tourist_spots public read seam (feature 015 — Q3, research R4).

``categories_for_spots`` groups each spot's category keys — the data route
and event emission use to inherit categories from their constituent spots.
Seeded through the owner repository (real rows).
"""

from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
    add_spot,
    replace_categories,
)
from passanorte_back.modules.tourist_spots.services.tourist_spots import (
    categories_for_spots,
)


def _seed(db_engine_session):
    with db_engine_session() as session:
        falls = add_spot(
            session,
            name="Seam Falls",
            description="d",
            latitude=-22.4,
            longitude=-45.0,
        )
        replace_categories(session, falls, ["nature", "leisure"])
        mirante = add_spot(
            session,
            name="Seam Mirante",
            description="d",
            latitude=-22.5,
            longitude=-45.1,
        )
        replace_categories(session, mirante, ["culture"])
        session.commit()
        return int(falls.id), int(mirante.id)


def test_categories_per_spot(sessionfactory_for) -> None:
    falls_id, mirante_id = _seed(sessionfactory_for)
    mapping = categories_for_spots(sessionfactory_for(), spot_ids=[falls_id, mirante_id])
    assert mapping == {falls_id: ["nature", "leisure"], mirante_id: ["culture"]}


def test_unknown_or_empty_ids_are_absent(sessionfactory_for) -> None:
    _seed(sessionfactory_for)
    mapping = categories_for_spots(sessionfactory_for(), spot_ids=[999])
    assert mapping == {}
    assert categories_for_spots(sessionfactory_for(), spot_ids=[]) == {}
