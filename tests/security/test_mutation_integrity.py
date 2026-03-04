from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_DIRS = (
    ROOT / "core",
    ROOT / "core" / "identity",
    ROOT / "interface",
    ROOT / "voice",
    ROOT / "services",
    ROOT / "apcos",
)

FORBIDDEN_IMPORT_MODULES = {
    "core.memory.lifecycle_manager",
    "core.memory.task_store",
}
FORBIDDEN_MUTATION_CALLS = {
    "create_task",
    "complete_task",
    "archive_task",
    "transition_task",
}

# Router is the sanctioned mutation gateway. Memory internals are allowed to
# reference lifecycle/mutation APIs by design.
ALLOWED_IMPORT_FILES = {
    Path("core/cognition/command_router.py"),
    Path("core/memory/task_store.py"),
}
ALLOWED_MUTATION_CALL_FILES = {
    Path("core/cognition/command_router.py"),
    Path("core/memory/task_store.py"),
}


def _iter_core_python_files() -> list[Path]:
    files: set[Path] = set()
    for folder in CORE_DIRS:
        if folder.exists():
            files.update(path for path in folder.rglob("*.py") if path.is_file())
    return sorted(files)


def _is_forbidden_module(module_name: str) -> bool:
    return any(
        module_name == forbidden or module_name.startswith(f"{forbidden}.")
        for forbidden in FORBIDDEN_IMPORT_MODULES
    )


def _parse_file(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _called_symbol_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_mutation_import_integrity() -> None:
    """Fail if non-router/non-memory files import lifecycle/task store modules."""
    violations: list[str] = []
    for file_path in _iter_core_python_files():
        rel_path = file_path.relative_to(ROOT)
        if rel_path in ALLOWED_IMPORT_FILES:
            continue

        tree = _parse_file(file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_module(alias.name):
                        violations.append(f"{rel_path}:{node.lineno} imports {alias.name}")
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _is_forbidden_module(module):
                    violations.append(f"{rel_path}:{node.lineno} imports from {module}")

    assert not violations, (
        "Unauthorized memory/lifecycle import usage detected:\n" + "\n".join(violations)
    )


def test_mutation_call_integrity() -> None:
    """Fail if mutation calls are referenced outside router/memory implementation."""
    violations: list[str] = []
    for file_path in _iter_core_python_files():
        rel_path = file_path.relative_to(ROOT)
        if rel_path in ALLOWED_MUTATION_CALL_FILES:
            continue

        tree = _parse_file(file_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = _called_symbol_name(node)
            if called in FORBIDDEN_MUTATION_CALLS:
                violations.append(f"{rel_path}:{node.lineno} calls {called}()")

    assert not violations, (
        "Unauthorized mutation call usage detected:\n" + "\n".join(violations)
    )
