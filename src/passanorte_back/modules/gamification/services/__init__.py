"""Module public service interface (the only cross-module importable surface).

``register_spot_visit`` is the sanctioned gamification seam: the visitation
module (spec 010) calls it — never this domain's repositories (research
R1/R12; constitution rules 3/5).
"""

from passanorte_back.modules.gamification.services.gamification import (  # noqa: F401
    register_spot_visit,
)

__all__ = ["register_spot_visit"]
