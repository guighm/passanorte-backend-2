"""Module Pydantic DTOs (private to the domain): side-effect import of the
schemas submodule, mirroring the other modules' package style."""

from passanorte_back.modules.gamification.schemas import gamification  # noqa: F401
from passanorte_back.modules.gamification.schemas.gamification import *  # noqa: F401,F403
