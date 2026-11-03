"""Contract: OpenAPI tags registry (feature 006; contracts/openapi-tags.md).

Cross-cutting sweep over the generated OpenAPI document: every operation
carries exactly one registered tag (FR-004/FR-005), the catalog is declared
with descriptions in canonical order (FR-006), and it stays 1:1 aligned with
the canonical ``DOMAIN_MODULES`` list (FR-002). Grouping mirrors the bounded
contexts (SC-005). Enforcement is test-suite-only (clarification Q1) — the
sweep names the offending path + method on failure (SC-004).
"""

from collections.abc import Iterator
from importlib import import_module
from typing import Any

from passanorte_back.core.modules import DOMAIN_MODULES
from passanorte_back.core.tags import (
    DOMAIN_TAG_NAMES,
    INFRASTRUCTURE_TAG,
    OPENAPI_TAGS_METADATA,
    module_tag,
)

# ``passanorte_back.__init__`` re-exports the ``main`` function, shadowing
# the subpackage — import_module under the full name (pattern of
# tests/smoke/test_health.py).
main_module = import_module("passanorte_back.main")
app = main_module.app

HTTP_METHODS = frozenset({"get", "post", "patch", "put", "delete", "head", "options"})

_MODULE_BY_SLUG: dict[str, str] = {name.replace("_", "-"): name for name in DOMAIN_MODULES}


def _openapi() -> dict[str, Any]:
    return app.openapi()


def _operations(doc: dict[str, Any]) -> Iterator[tuple[str, list[str] | None]]:
    """Yield ``(\"METHOD /path\", tags)`` for every documented operation."""
    for path, path_item in doc["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                identifier = f"{method.upper()} {path}"
                yield identifier, operation.get("tags")


def _expected_tag(path: str) -> str:
    """The only tag operation at ``path`` may carry (US3 group mapping)."""
    if path == "/health":
        return INFRASTRUCTURE_TAG
    slug = path.removeprefix("/api/v1/").split("/", maxsplit=1)[0]
    module = _MODULE_BY_SLUG[slug]
    return module_tag(module)


class TestPerOperationSweep:
    """FR-004/FR-005, SC-001/SC-002: every operation, one registered tag."""

    def test_every_operation_is_tagged(self) -> None:
        untagged = [identifier for identifier, tags in _operations(_openapi()) if not tags]
        assert not untagged, (
            f"untagged operations (fall into the Swagger default tag) — "
            f"declare their registry tag: {untagged}"
        )

    def test_no_operation_has_multiple_tags(self) -> None:
        multi_tagged = {
            identifier: tags
            for identifier, tags in _operations(_openapi())
            if tags and len(tags) != 1
        }
        assert not multi_tagged, (
            f"operations must carry exactly one registry tag, got multiple: {multi_tagged}"
        )

    def test_no_operation_uses_an_unregistered_tag(self) -> None:
        registered = {entry["name"] for entry in OPENAPI_TAGS_METADATA}
        unregistered = {
            (identifier, tuple(tags))
            for identifier, tags in _operations(_openapi())
            if tags and set(tags) - registered
        }
        assert not unregistered, (
            f"tags outside the central registry (core/tags.py): {sorted(unregistered)}"
        )

    def test_operation_tags_match_the_registry_constant(self) -> None:
        declared_tags = [entry["name"] for entry in OPENAPI_TAGS_METADATA]
        mismatched = {
            identifier: tags
            for identifier, tags in _operations(_openapi())
            if tags and tags != [tags[0]] or tags and tags[0] not in declared_tags
        }
        assert not mismatched, f"operations referencing dead constants: {mismatched}"


class TestCatalogDeclaration:
    """FR-006, SC-003 (clarifications Q2/Q3): the rendered catalog."""

    def test_catalog_declared_with_descriptions_in_order(self) -> None:
        doc = _openapi()
        doc_tags: list[dict[str, str]] = doc.get("tags")
        expected = [
            {"name": entry["name"], "description": entry["description"]}
            for entry in OPENAPI_TAGS_METADATA
        ]
        assert doc_tags == expected, (
            "OpenAPI catalog must equal the core/tags.py registry "
            "(names, descriptions, canonical order; Health last)"
        )

    def test_catalog_has_exactly_eleven_tags(self) -> None:
        doc = _openapi()
        doc_tags = doc.get("tags", [])
        assert len(doc_tags) == 11, (
            f"expected 10 domain tags + Health == 11 catalog entries, "
            f"got {len(doc_tags)}: {[t['name'] for t in doc_tags]}"
        )


class TestRegistryAlignment:
    """FR-002 (clarification Q3): 1:1 registry <-> DOMAIN_MODULES."""

    def test_domain_modules_map_bijectively_to_domain_tags(self) -> None:
        resolved = [module_tag(module) for module in DOMAIN_MODULES]
        assert set(resolved) == set(DOMAIN_TAG_NAMES), (
            "every canonical module must resolve to a distinct registry "
            f"tag: DOMAIN_MODULES={DOMAIN_MODULES} resolved={resolved}"
        )
        assert len(set(resolved)) == len(resolved), "duplicate tag names"

    def test_infrastructure_tag_is_outside_the_domain_mapping(self) -> None:
        resolved = {module_tag(module) for module in DOMAIN_MODULES}
        assert INFRASTRUCTURE_TAG not in resolved
        assert tuple(DOMAIN_TAG_NAMES) + (INFRASTRUCTURE_TAG,) == tuple(
            entry["name"] for entry in OPENAPI_TAGS_METADATA
        )

    def test_descriptions_match_the_contract_verbatim(self) -> None:
        expected: list[dict[str, str]] = [
            {
                "name": "Auth",
                "description": (
                    "Authentication and session management: login, token "
                    "refresh, logout and the current user identity (auth "
                    "module)."
                ),
            },
            {
                "name": "Employees",
                "description": (
                    "Employee management and benefit authorization (employees module)."
                ),
            },
            {
                "name": "Tourists",
                "description": (
                    "Tourist registration, login, profile and interests (tourists module)."
                ),
            },
            {
                "name": "Tourist Spots",
                "description": (
                    "Registered tourist spots with coordinates, schedules "
                    "and multilingual content (tourist_spots module)."
                ),
            },
            {
                "name": "Events",
                "description": "Cultural events and schedules (events module).",
            },
            {
                "name": "Gamification",
                "description": ("Routes, achievements and reward codes (gamification module)."),
            },
            {
                "name": "Visitation",
                "description": (

                        "GPS-validated check-ins at tourist spots: mark visitation "
                        "(RF31) with Haversine presence validation (RF32), the immutable "
                        "visitation ledger (RF33) and visitation history/visited-spots "
                        "projections (visitation module; feature 011)."

                ),
            },
            {
                "name": "Dashboard",
                "description": (
                    "Aggregated metrics and rankings for administrators (dashboard module)."
                ),
            },
            {
                "name": "Notifications",
                "description": ("Push notifications and communication (notifications module)."),
            },
            {
                "name": "Chatbot",
                "description": ("Generative chatbot over registered content (chatbot module)."),
            },
            {
                "name": "Health",
                "description": ("Operational health of the API and its database connectivity."),
            },
        ]
        assert expected == OPENAPI_TAGS_METADATA, (
            "registry descriptions must match contracts/openapi-tags.md verbatim"
        )


class TestGroupingMatchesModuleBoundaries:
    """US3, SC-005: groups mirror the bounded contexts exactly."""

    def test_every_operation_sits_under_exactly_its_domain_tag(self) -> None:
        mismatches = {
            identifier: tags
            for identifier, tags in _operations(_openapi())
            if not tags or tags != [_expected_tag(identifier.split(" ")[1])]
        }
        assert not mismatches, (
            "operations must sit exactly under the tag of their module's "
            f"bounded context: {mismatches}"
        )


def test_health_sits_under_only_the_infrastructure_tag() -> None:
    tags = dict(_operations(_openapi()))["GET /health"]
    assert tags == [INFRASTRUCTURE_TAG], f"GET /health tags: {tags}"
