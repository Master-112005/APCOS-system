from __future__ import annotations

from apcos import __main__ as module_entry


def test_module_main_starts_cli(monkeypatch) -> None:
    captured = {"called": False}

    def fake_run_shell(controller):  # type: ignore[no-untyped-def]
        captured["called"] = controller is not None

    monkeypatch.setattr(module_entry, "run_shell", fake_run_shell)
    exit_code = module_entry.main(["--config", "configs/default.yaml"])

    assert exit_code == 0
    assert captured["called"] is True


def test_module_main_returns_error_for_invalid_config(monkeypatch) -> None:
    def fake_run_shell(controller):  # type: ignore[no-untyped-def]
        _ = controller
        raise AssertionError("run_shell should not be called for invalid config")

    monkeypatch.setattr(module_entry, "run_shell", fake_run_shell)
    exit_code = module_entry.main(["--config", "configs/not-found.yaml"])

    assert exit_code == 1
