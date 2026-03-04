"""Startup readiness validation for APCOS bootstrap."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any, Mapping

from core.cognition.challenge_logic import ChallengeLogic
from core.cognition.command_router import CommandRouter, LifecycleManager, TaskStore


class StartupValidationError(RuntimeError):
    """Raised when APCOS startup prerequisites are not satisfied."""


REQUIRED_SECTIONS = ("command_router", "calibration", "proactive", "runtime", "hardware")
REQUIRED_DIRS = ("core", "interface", "voice", "services", "apcos", "configs")
MUTATION_SCAN_DIRS = ("core", "interface", "voice", "services", "apcos")
FORBIDDEN_IMPORT_MODULES = {
    "core.memory.lifecycle_manager",
    "core.memory.task_store",
}
ALLOWED_IMPORT_FILES = {
    Path("core/cognition/command_router.py"),
    Path("core/memory/task_store.py"),
}


def validate_startup(config: Mapping[str, Any], *, project_root: str | Path = ".") -> None:
    """
    Validate APCOS startup readiness.

    This function performs only validation checks and does not execute
    business logic, lifecycle mutations, or reasoning calls.
    """
    root = Path(project_root).resolve()
    _validate_config_sections(config)
    _validate_required_directories(root)
    _validate_import_integrity(root)
    _validate_module_imports()
    _validate_runtime_construction()


def _validate_config_sections(config: Mapping[str, Any]) -> None:
    missing = [section for section in REQUIRED_SECTIONS if section not in config]
    if missing:
        raise StartupValidationError(
            f"Startup configuration is missing required sections: {', '.join(missing)}"
        )


def _validate_required_directories(root: Path) -> None:
    missing = [name for name in REQUIRED_DIRS if not (root / name).exists()]
    if missing:
        raise StartupValidationError(
            f"Startup validation failed. Missing required directories: {', '.join(missing)}"
        )


def _validate_import_integrity(root: Path) -> None:
    violations: list[str] = []
    for folder_name in MUTATION_SCAN_DIRS:
        folder = root / folder_name
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            rel_path = path.relative_to(root)
            if rel_path in ALLOWED_IMPORT_FILES:
                continue

            source = path.read_text(encoding="utf-8")
            if (
                "core.memory.lifecycle_manager" not in source
                and "core.memory.task_store" not in source
            ):
                continue

            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if _is_forbidden_import(alias.name):
                            violations.append(
                                f"{rel_path}:{node.lineno} unauthorized import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if _is_forbidden_import(module):
                        violations.append(
                            f"{rel_path}:{node.lineno} unauthorized import from {module}"
                        )

    if violations:
        raise StartupValidationError(
            "Startup mutation integrity check failed:\n" + "\n".join(violations)
        )


def _is_forbidden_import(module_name: str) -> bool:
    return any(
        module_name == forbidden or module_name.startswith(f"{forbidden}.")
        for forbidden in FORBIDDEN_IMPORT_MODULES
    )


def _validate_module_imports() -> None:
    modules = (
        "apcos.bootstrap.config_loader",
        "apcos.bootstrap.logging_config",
        "apcos.bootstrap.container",
        "interface.interaction_controller",
        "interface.cli_shell",
        "core.cognition.command_router",
        "core.cognition.proactive_controller",
        "core.behavior.cpu_monitor",
        "core.behavior.memory_monitor",
        "core.behavior.thread_limiter",
        "core.behavior.power_state_manager",
        "core.behavior.resource_governor",
        "core.cognition.explanation_engine",
        "core.cognition.reasoning_engine",
        "core.identity.identity_context",
        "core.identity.identity_resolver",
        "core.identity.tier_policy",
        "core.identity.access_control",
        "voice.wake_word",
        "voice.audio_interface",
        "voice.asr_engine",
        "voice.audio_stream",
        "voice.model_manager",
        "voice.asr_engine_real",
        "voice.thread_safe_queue",
        "voice.transcription_worker",
        "voice.voice_identity_stub",
        "voice.voice_session",
        "voice.voice_controller",
        "voice.wake_word_engine",
        "services.hardware.battery_monitor",
        "services.hardware.capability_detector",
        "services.hardware.device_state_manager",
        "services.hardware.microphone_health",
        "services.hardware.sleep_manager",
        "services.hardware.thermal_monitor",
    )
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:
            raise StartupValidationError(
                f"Startup import check failed for module: {module}"
            ) from exc


def _validate_runtime_construction() -> None:
    try:
        lifecycle = LifecycleManager()
        store = TaskStore(lifecycle_manager=lifecycle)
        _ = CommandRouter(
            task_store=store,
            lifecycle_manager=lifecycle,
            challenge_logic=ChallengeLogic(),
            config_path="configs/default.yaml",
        )
        store.close()
    except Exception as exc:
        raise StartupValidationError("Startup dependency construction check failed.") from exc
