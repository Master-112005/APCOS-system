from __future__ import annotations

import ast
from pathlib import Path

from tests.validation.fixtures.energy_runtime_load import build_energy_runtime_harness


def test_llm_downgrade_during_active_cognition() -> None:
    harness = build_energy_runtime_harness()
    baseline_audits = harness.router_audit_count()

    harness.sync_burst(count=12, source_prefix="mobile")
    harness.set_battery(60)
    normal = harness.run_reasoning("Plan roadmap for next quarter with milestones.")

    harness.sync_burst(count=12, source_prefix="laptop")
    harness.set_battery(20)
    reduced = harness.run_reasoning("Plan roadmap for next quarter with milestones.")

    assert normal["allowed"] is True
    assert normal["mode"] == "NORMAL"
    assert normal["downgraded"] is False
    assert normal["steps"]

    assert reduced["allowed"] is True
    assert reduced["mode"] == "REDUCED"
    assert reduced["downgraded"] is True
    assert len(reduced["steps"]) <= len(normal["steps"])
    assert len(reduced["steps"]) <= 1

    assert harness.router_audit_count() == baseline_audits
    assert any(
        decision["mode"] == "NORMAL" and decision["execution_type"] == "LLM"
        for decision in harness.energy_state.decisions
    )
    assert any(
        decision["mode"] == "REDUCED" and decision["execution_type"] == "LLM"
        for decision in harness.energy_state.decisions
    )


def test_energy_runtime_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    target_dir = root / "tests" / "behavioral" / "energy_runtime"
    forbidden_exact = {"secure_storage", "energy_manager", "memory_authority"}
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

