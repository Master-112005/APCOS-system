from __future__ import annotations

from apcos.bootstrap.container import build_app
from interface.interaction_controller import InteractionController


def test_build_app_returns_interaction_controller() -> None:
    controller = build_app("configs/default.yaml")
    assert isinstance(controller, InteractionController)
