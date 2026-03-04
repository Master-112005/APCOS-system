from __future__ import annotations

from apcos import __main__ as module_entry


def test_main_uses_voice_loop_when_voice_flag_enabled(monkeypatch) -> None:
    calls = {"voice": False, "voice_real": False, "shell": False}

    def fake_build_voice_session(config_path, config=None, **kwargs):  # type: ignore[no-untyped-def]
        _ = (config_path, config, kwargs)
        return object()

    def fake_run_voice_loop(session):  # type: ignore[no-untyped-def]
        calls["voice"] = session is not None

    def fake_run_shell(controller):  # type: ignore[no-untyped-def]
        _ = controller
        calls["shell"] = True

    monkeypatch.setattr(module_entry, "build_voice_session", fake_build_voice_session)
    monkeypatch.setattr(module_entry, "run_voice_loop", fake_run_voice_loop)
    monkeypatch.setattr(module_entry, "run_shell", fake_run_shell)

    exit_code = module_entry.main(["--voice", "--config", "configs/default.yaml"])
    assert exit_code == 0
    assert calls["voice"] is True
    assert calls["voice_real"] is False
    assert calls["shell"] is False


def test_main_uses_real_voice_loop_when_voice_real_flag_enabled(monkeypatch) -> None:
    calls = {"voice": False, "voice_real": False, "shell": False}

    def fake_build_voice_session(config_path, config=None, **kwargs):  # type: ignore[no-untyped-def]
        _ = (config_path, config, kwargs)
        return object()

    def fake_build_real_voice_session(config_path, config=None, **kwargs):  # type: ignore[no-untyped-def]
        _ = (config_path, config, kwargs)
        calls["voice_real"] = True
        return object()

    def fake_run_voice_loop(session):  # type: ignore[no-untyped-def]
        calls["voice"] = session is not None

    def fake_run_shell(controller):  # type: ignore[no-untyped-def]
        _ = controller
        calls["shell"] = True

    monkeypatch.setattr(module_entry, "build_voice_session", fake_build_voice_session)
    monkeypatch.setattr(module_entry, "build_real_voice_session", fake_build_real_voice_session)
    monkeypatch.setattr(module_entry, "run_voice_loop", fake_run_voice_loop)
    monkeypatch.setattr(module_entry, "run_shell", fake_run_shell)

    exit_code = module_entry.main(["--voice-real", "--config", "configs/default.yaml"])
    assert exit_code == 0
    assert calls["voice_real"] is True
    assert calls["voice"] is True
    assert calls["shell"] is False


def test_real_voice_flag_does_not_affect_cli_mode(monkeypatch) -> None:
    calls = {"voice": False, "voice_real": False, "shell": False}

    def fake_build_voice_session(config_path, config=None, **kwargs):  # type: ignore[no-untyped-def]
        _ = (config_path, config, kwargs)
        calls["voice"] = True
        return object()

    def fake_build_real_voice_session(config_path, config=None, **kwargs):  # type: ignore[no-untyped-def]
        _ = (config_path, config, kwargs)
        calls["voice_real"] = True
        return object()

    def fake_run_voice_loop(session):  # type: ignore[no-untyped-def]
        _ = session
        calls["voice"] = True

    def fake_build_app(config_path, config=None):  # type: ignore[no-untyped-def]
        _ = (config_path, config)
        return object()

    def fake_run_shell(controller):  # type: ignore[no-untyped-def]
        _ = controller
        calls["shell"] = True

    monkeypatch.setattr(module_entry, "build_voice_session", fake_build_voice_session)
    monkeypatch.setattr(module_entry, "build_real_voice_session", fake_build_real_voice_session)
    monkeypatch.setattr(module_entry, "build_app", fake_build_app)
    monkeypatch.setattr(module_entry, "run_voice_loop", fake_run_voice_loop)
    monkeypatch.setattr(module_entry, "run_shell", fake_run_shell)

    exit_code = module_entry.main(["--config", "configs/default.yaml"])
    assert exit_code == 0
    assert calls["shell"] is True
    assert calls["voice_real"] is False


def test_runtime_governor_flag_overrides_default(monkeypatch) -> None:
    captured = {"runtime_governor_enabled": None}

    def fake_build_real_voice_session(config_path, config=None, **kwargs):  # type: ignore[no-untyped-def]
        _ = (config_path, config)
        captured["runtime_governor_enabled"] = kwargs.get("runtime_governor_enabled")
        return object()

    monkeypatch.setattr(module_entry, "build_real_voice_session", fake_build_real_voice_session)
    monkeypatch.setattr(module_entry, "run_voice_loop", lambda session: None)

    exit_code = module_entry.main(
        ["--voice-real", "--config", "configs/default.yaml", "--no-runtime-governor"]
    )
    assert exit_code == 0
    assert captured["runtime_governor_enabled"] is False
