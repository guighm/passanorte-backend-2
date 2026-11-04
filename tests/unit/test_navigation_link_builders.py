"""Unit: navigation deep-link builders (feature 013, T014 — research.md §R4).

Pure string builders, byte-exact (SC-004): decimal WGS-84 coordinates pass
through unchanged, destination/pickup roles never swap, provider selected
by configuration.
"""

from passanorte_back.modules.tourist_spots.services.navigation_links import (
    build_directions_map_link,
    build_navigation_links,
    build_ninety_nine_link,
    build_uber_link,
)

SPOT = (-22.4968, -45.0086)
ORIGIN = (-22.4901, -45.0001)


def test_google_maps_with_origin_is_directions_url() -> None:
    link = build_directions_map_link(*SPOT, origin=ORIGIN, provider="google_maps")
    assert link == (
        "https://www.google.com/maps/dir/?api=1"
        "&destination=-22.4968,-45.0086&origin=-22.4901,-45.0001"
    )


def test_google_maps_without_origin_matches_existing_search_link() -> None:
    link = build_directions_map_link(*SPOT, origin=None, provider="google_maps")
    assert link == "https://www.google.com/maps/search/?api=1&query=-22.4968,-45.0086"


def test_osm_provider_produces_osm_directions() -> None:
    link = build_directions_map_link(*SPOT, origin=ORIGIN, provider="osm")
    assert link == (
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car"
        "&route=-22.4901,-45.0001;-22.4968,-45.0086"
    )


def test_uber_link_carries_pickup_and_dropoff() -> None:
    link = build_uber_link(*SPOT, origin=ORIGIN)
    assert link == (
        "https://m.uber.com/ul/?action=setPickup"
        "&pickup[latitude]=-22.4901&pickup[longitude]=-45.0001"
        "&dropoff[latitude]=-22.4968&dropoff[longitude]=-45.0086"
    )


def test_uber_link_without_origin_falls_back_to_spot_self_pickup() -> None:
    link = build_uber_link(*SPOT, origin=None)
    assert link == (
        "https://m.uber.com/ul/?action=setPickup"
        "&pickup[latitude]=-22.4968&pickup[longitude]=-45.0086"
        "&dropoff[latitude]=-22.4968&dropoff[longitude]=-45.0086"
    )


def test_ninety_nine_link_is_app_scheme_with_coordinates() -> None:
    link = build_ninety_nine_link(*SPOT, origin=ORIGIN)
    assert link == (
        "99taxi://ride?pickupLatitude=-22.4901&pickupLongitude=-45.0001"
        "&dropLatitude=-22.4968&dropLongitude=-45.0086"
    )


def test_coordinate_precision_is_preserved_end_to_end() -> None:
    """Odd decimals survive verbatim — no float rounding, no swap (SC-004)."""
    precision_spot = (-22.496812345, -45.008612345)
    uber = build_uber_link(*precision_spot, origin=ORIGIN)
    assert "dropoff[latitude]=-22.496812345&dropoff[longitude]=-45.008612345" in uber
    pickup = build_ninety_nine_link(*precision_spot, origin=ORIGIN)
    assert pickup.endswith("dropLatitude=-22.496812345&dropLongitude=-45.008612345")


def test_build_navigation_links_bundle_and_provider_switch() -> None:
    """The bundle returns origin + three links; provider only moves mapLink
    (SC-007: same shape, targets follow configuration)."""
    google = build_navigation_links(*SPOT, origin=ORIGIN, provider="google_maps")
    osm = build_navigation_links(*SPOT, origin=ORIGIN, provider="osm")
    assert set(google) == {"origin", "mapLink", "uberLink", "ninetyNineLink"}
    assert set(osm) == set(google)
    assert google["mapLink"] != osm["mapLink"]
    assert "openstreetmap" in osm["mapLink"]
    assert google["uberLink"] == osm["uberLink"]
    assert google["ninetyNineLink"] == osm["ninetyNineLink"]
    assert google["origin"] == {"latitude": ORIGIN[0], "longitude": ORIGIN[1]}


def test_osm_without_origin_is_marker_link() -> None:
    """T025 (plan §R4): destination-only OSM cannot produce directions —
    the documented shape is the map marker pin for the spot."""
    link = build_directions_map_link(*SPOT, origin=None, provider="osm")
    assert link == "https://www.openstreetmap.org/?mlat=-22.4968&mlon=-45.0086#map=17/"
