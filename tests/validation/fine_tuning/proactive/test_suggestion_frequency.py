from __future__ import annotations

import ast
from pathlib import Path

from core.cognition.proactive_controller import ProactiveController


def _rich_context() -> dict[str, float | int]:
    return {
        "overdue_tasks": 2,
        "scheduled_tasks_today": 11,
        "daily_capacity": 7,
        "goal_alignment_score": 0.3,
    }


def test_suggestion_frequency_window_limit_applies() -> None:
    controller = ProactiveController(
        confidence_threshold=0.7,
        daily_limit=20,
        recent_suggestion_window=5,
        max_suggestions_per_window=2,
        repetition_cooldown_steps=1,
    )

    first = controller.evaluate(_rich_context())
    second = controller.evaluate(_rich_context())

    assert len(first) == 2
    assert second == []


def test_proactive_fine_tuning_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[4]
    target_dir = root / "tests" / "validation" / "fine_tuning" / "proactive"
    forbidden_exact = {"memory_authority", "secure_storage"}
    forbidden_prefixes = ("os.src", "os.src.runtime", "os.src.identity")

    violations: list[str] = []
    for file_path in sorted(target_dir.glob("test_*.py")):
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith(forbidden_prefixes) or name in forbidden_exact:
                        violations.append(f"{file_path}:{node.lineno}:{name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(forbidden_prefixes) or module in forbidden_exact:
                    violations.append(f"{file_path}:{node.lineno}:{module}")

    assert not violations, "Forbidden imports detected:\n" + "\n".join(violations)

