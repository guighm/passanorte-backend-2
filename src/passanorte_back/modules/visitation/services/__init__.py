"""Module public service interface (the only cross-module importable surface).

Feature 011: no other module consumes visitation yet (the dashboard is a
future consumer of the ledger); the flows stay importable via this
package per the constitution rule 3.
"""

from passanorte_back.modules.visitation.services.visitations import (
    OutsideToleranceError,
    TouristMissingError,
    list_visitations,
    list_visited_spots,
    mark_visitation,
)

__all__ = [
    "OutsideToleranceError",
    "TouristMissingError",
    "list_visited_spots",
    "list_visitations",
    "mark_visitation",
]
