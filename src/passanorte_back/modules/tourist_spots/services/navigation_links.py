"""Navigation deep-link builders (feature 013 — RF28, RNF18; T016).

Pure string builders, unit-testable byte-exact, NO network calls, never
stored (read-time computation only — FR-008/R10 inheritance). All targets
are free, publicly documented URL/scheme forms (RNF15):

- Google Maps (default provider): ``maps/dir`` with ``destination`` and,
  when an origin is given, ``origin``; destination-only keeps the existing
  ``maps/search`` link shape of ``tourist_spots.build_map_link`` (spec 007).
- OpenStreetMap (configurable alternative — RNF18):
  ``openstreetmap.org/directions`` with the OSRM car engine and a
  ``route=<origin>;<destination>`` path.
- Uber: ``m.uber.com/ul`` universal link (web fallback when the app is
  absent): ``pickup`` = tourist position, ``dropoff`` = the spot.
- 99: ``99taxi://ride`` public app scheme (no free web fallback exists):
  ``pickup*`` = tourist position, ``drop*`` = the spot.

Without a tourist position the fallback origin IS the spot's own
coordinates (FR-010 — self-documented in the response's ``origin`` field).
Coordinates cross verbatim: no rounding, no origin/destination swap
(SC-004). ``discovery_map_provider`` selects only the map builder — SC-007
provider switch changes targets, never status codes or response shapes.
"""

from urllib.parse import quote

GOOGLE_MAPS_PROVIDER = "google_maps"
OSM_PROVIDER = "osm"

MAP_PROVIDERS = (GOOGLE_MAPS_PROVIDER, OSM_PROVIDER)


def _coordinate(value: float) -> str:
    """Decimal WGS-84 passthrough: shortest exact representation.

    ``repr`` of a float round-trips exactly; trailing zeros of whole
    degrees collapse the same way the existing ``build_map_link`` does.
    """
    text = f"{value!r}"
    if text.endswith(".0"):
        text = text[:-2]
    return quote(text)


def _normalize_origin(
    latitude: float, longitude: float, origin: tuple[float, float] | None
) -> tuple[float, float]:
    """Fallback origin (FR-010): the spot's own location when none given."""
    return origin if origin is not None else (latitude, longitude)


def build_directions_map_link(
    latitude: float, longitude: float, *, origin: tuple[float, float] | None, provider: str
) -> str:
    """Provider-selected map directions link (RNF18 — config-only switch)."""
    destination = f"{_coordinate(latitude)},{_coordinate(longitude)}"
    if provider == OSM_PROVIDER:
        if origin is None:
            return f"https://www.openstreetmap.org/?mlat={_coordinate(latitude)}&mlon={_coordinate(longitude)}#map=17/"
        route = f"{_coordinate(origin[0])},{_coordinate(origin[1])};{destination}"
        return f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route={route}"
    # google_maps: destination-only keeps the established search shape.
    if origin is None:
        return f"https://www.google.com/maps/search/?api=1&query={destination}"
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={destination}"
        f"&origin={_coordinate(origin[0])},{_coordinate(origin[1])}"
    )


def build_uber_link(latitude: float, longitude: float, origin: tuple[float, float] | None) -> str:
    pickup_latitude, pickup_longitude = _normalize_origin(latitude, longitude, origin)
    return (
        "https://m.uber.com/ul/?action=setPickup"
        f"&pickup[latitude]={_coordinate(pickup_latitude)}"
        f"&pickup[longitude]={_coordinate(pickup_longitude)}"
        f"&dropoff[latitude]={_coordinate(latitude)}"
        f"&dropoff[longitude]={_coordinate(longitude)}"
    )


def build_ninety_nine_link(
    latitude: float, longitude: float, origin: tuple[float, float] | None
) -> str:
    pickup_latitude, pickup_longitude = _normalize_origin(latitude, longitude, origin)
    return (
        "99taxi://ride"
        f"?pickupLatitude={_coordinate(pickup_latitude)}"
        f"&pickupLongitude={_coordinate(pickup_longitude)}"
        f"&dropLatitude={_coordinate(latitude)}"
        f"&dropLongitude={_coordinate(longitude)}"
    )


def build_navigation_links(
    latitude: float,
    longitude: float,
    *,
    origin: tuple[float, float] | None,
    provider: str,
) -> dict[str, object]:
    """The ready-to-open triple plus the effective origin (contracts §2)."""
    effective = _normalize_origin(latitude, longitude, origin)
    return {
        "origin": {"latitude": effective[0], "longitude": effective[1]},
        "mapLink": build_directions_map_link(latitude, longitude, origin=origin, provider=provider),
        "uberLink": build_uber_link(latitude, longitude, origin),
        "ninetyNineLink": build_ninety_nine_link(latitude, longitude, origin),
    }
