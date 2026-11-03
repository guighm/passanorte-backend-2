"""Module data access (private to the domain): side-effect import of the
repositories submodule, mirroring the other modules' package style."""

from passanorte_back.modules.gamification.repositories import gamification  # noqa: F401
from passanorte_back.modules.gamification.repositories.gamification import *  # noqa: F401,F403
