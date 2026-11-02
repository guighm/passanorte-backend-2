"""Public service interface of the ``events`` module.

``list_public_spot_events`` is the seam consumed by the tourist_spots
public detail (constitution rules 3/5 — cross-module only via this public
service function, never by touching events tables from another module):
when the events milestone ships its data, this is the single function
that grows the real query. Until then it answers the empty collection —
never an error (feature 007 spec assumption / research R8).
"""

from sqlalchemy.orm import Session


def list_public_spot_events(session: Session, spot_id: int) -> list[dict[str, object]]:
    """Events associated to a tourist spot, as exposed publicly.

    Returns ``[]`` until the events domain persists its data (feature 007
    assumption); the tourist_spots public detail embeds this result
    verbatim — a spot with no associated events renders an empty list.
    """
    return []
