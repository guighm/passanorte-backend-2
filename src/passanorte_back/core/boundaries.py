"""Verificação automatizada de fronteiras entre módulos (FR-004/FR-005).

Varredura AST de um pacote de domínio: importar internals privados de outro
módulo (``schemas``/``repositories``/``routes``/símbolos com prefixo ``_``)
gera violação com módulo e arquivo nomeados. Importar ``<módulo>.services``
(interface de serviço pública), ``core.*`` e ``main`` é permitido
(constituição, regras 3/5).

``tests/smoke/test_boundaries.py`` executa esta verificação contra o código
real e prova sua eficácia com arquivos violadores gerados em memória.
"""

import ast
from pathlib import Path
from typing import Final

from passanorte_back.core.modules import DOMAIN_MODULES

PACKAGE_ROOT = "passanorte_back"

# Camadas privadas ao domínio; apenas ``services`` é superfície pública.
PRIVATE_LAYERS: Final[frozenset[str]] = frozenset({"routes", "repositories", "schemas"})


def _violation_message(
    source_module: str, relative_file: Path, target_module: str, detail: str
) -> str:
    return (
        f"[fronteira] módulo '{source_module}' importa interno privado de "
        f"'{target_module}' ({detail}) — arquivo: {relative_file}"
    )


def _check_target(
    source_module: str,
    relative_file: Path,
    target_path: str,
    symbols: tuple[str, ...],
    violations: list[str],
) -> None:
    """Avalia um import alvo ``<módulo>[.<camada>...]`` (sem raiz do pacote)."""
    parts = target_path.split(".")
    first = parts[0]
    if first == source_module or first not in DOMAIN_MODULES:
        return  # core, main e o próprio módulo são liberados
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
    """Resolve ``node.module`` (absoluto ou relativo) em caminho do pacote.

    ``package_parts`` é o caminho do pacote do arquivo (ex.: ``("auth",
    "services")``). ``node.level`` sobe ``level - 1`` níveis a partir dele.
    """
    if not node.level:  # absoluto: o caminho do node já é completo
        return node.module or None
    base = package_parts[: len(package_parts) - max(node.level - 1, 0)]
    segments = [segment for segment in (*base, node.module or "") if segment]
    if not segments:
        return None
    return ".".join(segments)


def find_boundary_violations(package_dir: Path) -> list[str]:
    """Retorna uma mensagem por violação; lista vazia = fronteiras íntegras."""
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
                                alias.name.removeprefix(f"{PACKAGE_ROOT}."),
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
                        target.removeprefix(f"{PACKAGE_ROOT}."),
                        tuple(alias.name for alias in node.names),
                        violations,
                    )
    return violations
