"""Public service interface of the tourist_spots module.

Cross-module consumers (e.g. visitation, chatbot) call these functions —
never the repositories/schemas internals (constitution rule 3).
"""

from passanorte_back.modules.tourist_spots.services.tourist_spots import (
    build_map_link,
    build_public_detail,
    create_spot,
    get_active_spot,
    remove_spot,
    spot_to_view,
    update_spot,
)

__all__ = [
    "build_map_link",
    "build_public_detail",
    "create_spot",
    "get_active_spot",
    "remove_spot",
    "spot_to_view",
    "update_spot",
]
