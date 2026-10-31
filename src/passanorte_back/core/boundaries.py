"""Automated boundary verification between modules (FR-004/FR-005).

AST scan of a domain package: importing another module's private internals
(``schemas``/``repositories``/``routes``/symbols with a ``_`` prefix)
produces a violation naming the module and the file. Importing
``<module>.services`` (public service interface), ``core.*`` and ``main``
is allowed (constitution, rules 3/5). Absolute imports live under
``passanorte_back.modules.<module>...`` — the root prefix and the
``modules`` segment are removed before evaluation.

``tests/smoke/test_boundaries.py`` runs this check against the real code
and proves its effectiveness with in-memory violator files.
"""

import ast
from pathlib import Path
from typing import Final

from passanorte_back.core.modules import DOMAIN_MODULES

PACKAGE_ROOT = "passanorte_back"
MODULES_SEGMENT = "modules"  # groups the domain modules under the package


def _module_target(full_path: str) -> str:
    """Strip ``passanorte_back[.modules]`` from an absolute import path."""
    return full_path.removeprefix(f"{PACKAGE_ROOT}.").removeprefix(f"{MODULES_SEGMENT}.")


# Layers private to the domain; only ``services`` is the public surface.
PRIVATE_LAYERS: Final[frozenset[str]] = frozenset({"routes", "repositories", "schemas"})


def _violation_message(
    source_module: str, relative_file: Path, target_module: str, detail: str
) -> str:
    return (
        f"[boundary] module '{source_module}' imports private internals of "
        f"'{target_module}' ({detail}) — file: {relative_file}"
    )


def _check_target(
    source_module: str,
    relative_file: Path,
    target_path: str,
    symbols: tuple[str, ...],
    violations: list[str],
) -> None:
    """Evaluate a target import ``<module>[.<layer>...]`` (without the package
    root or the ``modules`` segment)."""
    parts = target_path.split(".")
    first = parts[0]
    if first == source_module or first not in DOMAIN_MODULES:
        return  # core, main and the module itself are exempt
    layer = parts[1] if len(parts) > 1 else ""
    if layer.startswith("_"):
        violations.append(_violation_message(source_module, relative_file, first, layer))
        return
    if layer in PRIVATE_LAYERS:
        violations.append(_violation_message(source_module, relative_file, first, layer))
        return
    if layer in ("", "services"):
        for symbol in symbols:
            if symbol.startswith("_"):
                violations.append(_violation_message(source_module, relative_file, first, symbol))


def _resolve_target(node: ast.ImportFrom, package_parts: tuple[str, ...]) -> str | None:
    """Resolve ``node.module`` (absolute or relative) into a package path.

    ``package_parts`` is the package path of the file (e.g. ``("auth",
    "services")``). ``node.level`` climbs ``level - 1`` levels from it.
    """
    if not node.level:  # absolute: node path is already the full import path
        return node.module or None
    base = package_parts[: len(package_parts) - max(node.level - 1, 0)]
    segments = [segment for segment in (*base, node.module or "") if segment]
    if not segments:
        return None
    return ".".join(segments)


def find_boundary_violations(package_dir: Path) -> list[str]:
    """Return one message per violation; empty list = boundaries intact."""
    violations: list[str] = []
    for module in DOMAIN_MODULES:
        module_dir = package_dir / module
        if not module_dir.is_dir():
            continue
        for file in sorted(module_dir.rglob("*.py")):
            relative = file.relative_to(package_dir)
            if relative.parts[0] != module:
                continue
            package_parts = tuple(relative.parts[:-1])
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(f"{PACKAGE_ROOT}."):
                            _check_target(
                                module,
                                relative,
                                _module_target(alias.name),
                                (),
                                violations,
                            )
                elif isinstance(node, ast.ImportFrom):
                    target = _resolve_target(node, package_parts)
                    if target is None or not target.startswith(f"{PACKAGE_ROOT}."):
                        continue
                    _check_target(
                        module,
                        relative,
                        _module_target(target),
                        tuple(alias.name for alias in node.names),
                        violations,
                    )
    return violations
