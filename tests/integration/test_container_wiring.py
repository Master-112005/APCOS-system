from __future__ import annotations

from apcos.bootstrap.config_loader import load_config
from apcos.bootstrap.container import (
    AppContainer,
    build_app,
    build_real_voice_session,
    build_voice_session,
)
from interface.interaction_controller import InteractionController
from voice.voice_session import RealVoiceSession, VoiceSession


def test_container_builds_all_runtime_components() -> None:
    config = load_config("configs/default.yaml")
    container = AppContainer(config=config, config_path="configs/default.yaml")

    assert container.lifecycle is not None
    assert container.task_store is not None
    assert container.command_router is not None
    assert container.proactive_controller is not None
    assert container.explanation_engine is not None
    assert container.reasoning_engine is not None
    assert container.identity_resolver is not None
    assert container.access_control is not None
    assert isinstance(container.controller, InteractionController)


def test_build_app_loads_config_once_when_not_provided(monkeypatch) -> None:
    from apcos.bootstrap import container as container_module

    original = container_module.load_config
    calls = {"count": 0}

    def spy(path):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return original(path)

    monkeypatch.setattr(container_module, "load_config", spy)

    controller = build_app("configs/default.yaml")
    assert isinstance(controller, InteractionController)
    assert calls["count"] == 1


def test_build_app_uses_injected_config_without_reloading(monkeypatch) -> None:
    from apcos.bootstrap import container as container_module

    calls = {"count": 0}

    def spy(path):  # type: ignore[no-untyped-def]
        _ = path
        calls["count"] += 1
        return {}

    config = load_config("configs/default.yaml")
    monkeypatch.setattr(container_module, "load_config", spy)
    controller = build_app("configs/default.yaml", config=config)

    assert isinstance(controller, InteractionController)
    assert calls["count"] == 0


def test_build_voice_session_returns_voice_session() -> None:
    session = build_voice_session("configs/default.yaml")
    assert isinstance(session, VoiceSession)


def test_build_real_voice_session_returns_real_voice_session() -> None:
    session = build_real_voice_session("configs/default.yaml")
    assert isinstance(session, RealVoiceSession)
