"""Module HTTP routes (tourist_spots): imported for side effect — decorators
on the canonical router (core/routers.py).

The admin listing (fixed path ``""``) is decorated before the
parameterized paths; the public detail (`GET /{spot_id}`, US5) shares the
``/{spot_id}`` path with PATCH/DELETE (different methods — no conflict).
"""

from passanorte_back.modules.tourist_spots.routes import tourist_spots  # noqa: F401
