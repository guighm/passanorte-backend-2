"""Smoke: fronteiras entre módulos via AST (FR-004/FR-005; research R5).

A verificação varre ``src/passanorte_back`` e falha ao importar internals
privados de outro módulo (``schemas``, ``repositories``, ``routes`` ou
símbolos com prefixo ``_``). Import de ``<módulo>.services``, ``core.*`` e
``main`` é permitido. O teste negativo embutido prova a eficácia: um arquivo
violador gerado em memória produz violação apontando módulo e arquivo.
"""

from pathlib import Path

from passanorte_back.core.boundaries import find_boundary_violations
from passanorte_back.core.modules import DOMAIN_MODULES

SRC_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "passanorte_back"

# ``core`` é infraestrutura comum (não é módulo de domínio).
NON_DOMAIN_PACKAGES = {"core"}


def test_package_matches_the_ten_module_list() -> None:
    present = {
        d.name for d in SRC_PACKAGE.iterdir() if d.is_dir() and (d / "__init__.py").exists()
    } - NON_DOMAIN_PACKAGES
    assert present == set(DOMAIN_MODULES)


def test_real_codebase_has_zero_boundary_violations() -> None:
    violations = find_boundary_violations(SRC_PACKAGE)
    assert violations == []


def test_detection_proofs_against_deliberate_violation(tmp_path: Path) -> None:
    """Teste negativo: arquivo violador em memória gera violação nomeando
    módulo e arquivo ofensores (cenário 4 da US-2)."""
    guilty = tmp_path / "funcionarios" / "services" / "__init__.py"
    guilty.parent.mkdir(parents=True)
    guilty.write_text(
        "from passanorte_back.turistas.schemas import TuristaIn\n",
        encoding="utf-8",
    )
    violations = find_boundary_violations(tmp_path)

    assert len(violations) == 1
    assert "funcionarios" in violations[0]
    assert "turistas" in violations[0]
    assert "schemas" in violations[0]


def test_private_symbol_import_is_flagged(tmp_path: Path) -> None:
    guilty = tmp_path / "dashboard" / "services" / "__init__.py"
    guilty.parent.mkdir(parents=True)
    guilty.write_text(
        "from passanorte_back.eventos._internal import build\n",
        encoding="utf-8",
    )
    violations = find_boundary_violations(tmp_path)
    assert len(violations) == 1
    assert "_internal" in violations[0]


def test_services_import_across_modules_is_allowed(tmp_path: Path) -> None:
    allowed = tmp_path / "gamificacao" / "services" / "__init__.py"
    allowed.parent.mkdir(parents=True)
    allowed.write_text(
        "from passanorte_back.visitacao.services import register_visit\n",
        encoding="utf-8",
    )
    assert find_boundary_violations(tmp_path) == []
