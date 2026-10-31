"""Smoke: module boundaries via AST (FR-004/FR-005; research R5).

The check scans ``src/passanorte_back/modules`` and fails on importing
another module's private internals (``schemas``, ``repositories``,
``routes`` or ``_``-prefixed symbols). Import of ``<module>.services``,
``core.*`` and ``main`` is allowed. The built-in negative test proves
effectiveness: an in-memory violator file yields a violation naming the
offending module and file.
"""

from pathlib import Path

from passanorte_back.core.boundaries import find_boundary_violations
from passanorte_back.core.modules import DOMAIN_MODULES

MODULES_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "passanorte_back" / "modules"


def test_package_matches_the_ten_module_list() -> None:
    present = {
        d.name for d in MODULES_PACKAGE.iterdir() if d.is_dir() and (d / "__init__.py").exists()
    }
    assert present == set(DOMAIN_MODULES)


def test_real_codebase_has_zero_boundary_violations() -> None:
    violations = find_boundary_violations(MODULES_PACKAGE)
    assert violations == []


def test_detection_proofs_against_deliberate_violation(tmp_path: Path) -> None:
    """Negative test: an in-memory violator file yields a violation naming
    the offending module and file (US-2 scenario 4)."""
    guilty = tmp_path / "employees" / "services" / "__init__.py"
    guilty.parent.mkdir(parents=True)
    guilty.write_text(
        "from passanorte_back.modules.tourists.schemas import TuristaIn\n",
        encoding="utf-8",
    )
    violations = find_boundary_violations(tmp_path)

    assert len(violations) == 1
    assert "employees" in violations[0]
    assert "tourists" in violations[0]
    assert "schemas" in violations[0]


def test_private_symbol_import_is_flagged(tmp_path: Path) -> None:
    guilty = tmp_path / "dashboard" / "services" / "__init__.py"
    guilty.parent.mkdir(parents=True)
    guilty.write_text(
        "from passanorte_back.modules.events._internal import build\n",
        encoding="utf-8",
    )
    violations = find_boundary_violations(tmp_path)
    assert len(violations) == 1
    assert "_internal" in violations[0]


def test_services_import_across_modules_is_allowed(tmp_path: Path) -> None:
    allowed = tmp_path / "gamification" / "services" / "__init__.py"
    allowed.parent.mkdir(parents=True)
    allowed.write_text(
        "from passanorte_back.modules.visitation.services import register_visit\n",
        encoding="utf-8",
    )
    assert find_boundary_violations(tmp_path) == []
