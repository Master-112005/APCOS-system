from __future__ import annotations

import os
from time import perf_counter

from apcos.bootstrap.config_loader import load_config
from apcos.bootstrap.container import AppContainer
from apcos.bootstrap.startup_validator import validate_startup


def test_bootstrap_startup_performance_within_budget() -> None:
    max_startup_seconds = float(os.getenv("APCOS_BOOTSTRAP_PERF_MAX_SEC", "0.2"))

    start = perf_counter()
    config = load_config("configs/default.yaml")
    config_elapsed = perf_counter() - start

    start = perf_counter()
    validate_startup(config, project_root=".")
    validation_elapsed = perf_counter() - start

    start = perf_counter()
    container = AppContainer(config=config, config_path="configs/default.yaml")
    _ = container.controller
    container_elapsed = perf_counter() - start

    total = config_elapsed + validation_elapsed + container_elapsed
    assert total < max_startup_seconds, (
        "Bootstrap performance budget exceeded: "
        f"total={total:.6f}s max={max_startup_seconds:.6f}s "
        f"(config={config_elapsed:.6f}s validation={validation_elapsed:.6f}s "
        f"container={container_elapsed:.6f}s)"
    )
