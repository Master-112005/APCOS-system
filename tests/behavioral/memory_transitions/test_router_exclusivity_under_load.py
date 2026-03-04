from __future__ import annotations

from typing import Any

from tests.validation.fixtures.memory_transition_load import build_memory_transition_harness


def _guard_method(
    *,
    target: Any,
    method_name: str,
    gate: dict[str, bool],
    counters: dict[str, int],
    monkeypatch: Any,
) -> None:
    original = getattr(target, method_name)

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        if not gate["in_route"]:
            raise AssertionError(f"{method_name} called outside router.route")
        counters[method_name] = counters.get(method_name, 0) + 1
        return original(*args, **kwargs)

    monkeypatch.setattr(target, method_name, _wrapped)


def test_router_exclusivity_under_load(monkeypatch: Any) -> None:
    harness = build_memory_transition_harness()
    task_count = 15  # 60 routed mutation attempts total.

    gate = {"in_route": False}
    counters: dict[str, int] = {}
    original_route = harness.router.route

    def _guarded_route(intent_object: dict[str, object]) -> Any:
        gate["in_route"] = True
        try:
            return original_route(intent_object)
        finally:
            gate["in_route"] = False

    monkeypatch.setattr(harness.router, "route", _guarded_route)

    _guard_method(
        target=harness.store,
        method_name="create_task",
        gate=gate,
        counters=counters,
        monkeypatch=monkeypatch,
    )
    _guard_method(
        target=harness.store,
        method_name="activate_task",
        gate=gate,
        counters=counters,
        monkeypatch=monkeypatch,
    )
    _guard_method(
        target=harness.store,
        method_name="transition_task",
        gate=gate,
        counters=counters,
        monkeypatch=monkeypatch,
    )
    _guard_method(
        target=harness.store,
        method_name="complete_task",
        gate=gate,
        counters=counters,
        monkeypatch=monkeypatch,
    )
    _guard_method(
        target=harness.store,
        method_name="archive_task",
        gate=gate,
        counters=counters,
        monkeypatch=monkeypatch,
    )
    _guard_method(
        target=harness.lifecycle,
        method_name="assert_transition",
        gate=gate,
        counters=counters,
        monkeypatch=monkeypatch,
    )

    task_ids = [
        harness.create_task(title=f"Guard Task {index}", intent_id=f"guard-create-{index}")
        for index in range(task_count)
    ]
    for index, task_id in enumerate(task_ids):
        assert (
            harness.activate_task(task_id=task_id, intent_id=f"guard-activate-{index}").status
            == "executed"
        )
    for index, task_id in enumerate(task_ids):
        assert (
            harness.complete_task(task_id=task_id, intent_id=f"guard-complete-{index}").status
            == "executed"
        )
    for index, task_id in enumerate(task_ids):
        assert (
            harness.archive_task(task_id=task_id, intent_id=f"guard-archive-{index}").status
            == "executed"
        )

    assert counters.get("create_task", 0) == task_count
    assert counters.get("complete_task", 0) == task_count
    assert counters.get("archive_task", 0) == task_count
    assert counters.get("transition_task", 0) == task_count * 3
    assert counters.get("assert_transition", 0) == task_count * 3
    assert len(harness.router.get_audit_events()) == task_count * 4
