"""Module HTTP routes (gamification): imported for side effect — decorators
on the canonical router (core/routers.py). Fixed paths ("" listing,
enrollments) are decorated before parameterized paths."""

from passanorte_back.modules.gamification.routes import gamification  # noqa: F401
