from __future__ import annotations

import ast
from pathlib import Path

from core.cognition.reasoning_engine import ReasoningEngine


class CommandPatternLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        return (
            "You should create_task(title='Ship review') then update_task(id=4, status='done') "
            "and archive(task_id=9)."
        )


class PlanningLLMClient:
    def generate(self, prompt: str) -> str:
        _ = prompt
        return (
            "Start with three key outcomes for the week. "
            "Break each outcome into small milestones. "
            "Reserve protected focus blocks and review at end of day."
        )


def test_reasoning_filters_mutation_command_patterns() -> None:
    engine = ReasoningEngine(llm_client=CommandPatternLLMClient())
    output = engine.generate_strategy({"goal": "organize work"})

    assert output.safe_to_present is True
    assert output.summary == "This is an explanation only. Actions require user confirmation."
    rendered = f"{output.summary} {' '.join(output.strategy_steps)}".lower()
    forbidden = ("create_task(", "update_task(", "archive(", "delete(")
    assert not any(token in rendered for token in forbidden)


def test_ambiguous_request_stays_advisory() -> None:
    engine = ReasoningEngine(llm_client=PlanningLLMClient())
    output = engine.generate_strategy({"goal": "maybe change my tasks"})

    assert output.safe_to_present is True
    assert "explanation only" in output.summary.lower()
    assert output.strategy_steps
    rendered = f"{output.summary} {' '.join(output.strategy_steps)}".lower()
    assert "create_task(" not in rendered
    assert "archive(" not in rendered


def test_reasoning_fine_tuning_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[4]
    target_dir = root / "tests" / "validation" / "fine_tuning" / "reasoning"
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
