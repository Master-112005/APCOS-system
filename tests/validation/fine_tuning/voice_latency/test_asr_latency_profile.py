from __future__ import annotations

import ast
from pathlib import Path

from voice.asr_engine import ASREngine


def test_asr_latency_profile_shows_cache_reuse() -> None:
    engine = ASREngine()
    audio = b"tier:owner;text:Schedule reading tomorrow at 9"

    first_text = engine.transcribe(audio)
    first_profile = engine.profile_snapshot()

    second_text = engine.transcribe(audio)
    second_profile = engine.profile_snapshot()

    assert first_text == "Schedule reading tomorrow at 9"
    assert second_text == "Schedule reading tomorrow at 9"

    assert first_profile["cold_start"] is True
    assert second_profile["cold_start"] is False
    assert second_profile["cache_reused"] is True
    assert second_profile["model_load_count"] == 1
    assert second_profile["pipeline_build_count"] == 1
    assert second_profile["total_latency_ms"] < first_profile["total_latency_ms"]


def test_voice_latency_static_safety_imports() -> None:
    root = Path(__file__).resolve().parents[4]
    target_dir = root / "tests" / "validation" / "fine_tuning" / "voice_latency"
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

