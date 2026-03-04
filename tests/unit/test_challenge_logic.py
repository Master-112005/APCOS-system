from __future__ import annotations

from core.cognition.challenge_logic import ChallengeLogic


def test_challenge_issued_for_low_alignment() -> None:
    logic = ChallengeLogic(challenge_threshold=0.5)
    challenge = logic.evaluate(
        task_id=1,
        proposed_action="Skip workout for gaming",
        declared_goal="Improve fitness",
        alignment_score=0.2,
    )

    assert challenge is not None
    assert challenge["task_id"] == 1
    assert challenge["alignment_score"] == 0.2


def test_only_one_challenge_per_task_action() -> None:
    logic = ChallengeLogic(challenge_threshold=0.5)
    first = logic.evaluate(
        task_id=1,
        proposed_action="Skip workout for gaming",
        declared_goal="Improve fitness",
        alignment_score=0.2,
    )
    second = logic.evaluate(
        task_id=1,
        proposed_action="Skip workout for gaming",
        declared_goal="Improve fitness",
        alignment_score=0.1,
    )

    assert first is not None
    assert second is None


def test_rejected_challenge_is_not_repeated() -> None:
    logic = ChallengeLogic(challenge_threshold=0.5)
    first = logic.evaluate(
        task_id=7,
        proposed_action="Cancel deep-work block",
        declared_goal="Finish key project",
        alignment_score=0.1,
    )
    assert first is not None

    logic.record_response(task_id=7, proposed_action="Cancel deep-work block", accepted=False)
    second = logic.evaluate(
        task_id=7,
        proposed_action="Cancel deep-work block",
        declared_goal="Finish key project",
        alignment_score=0.1,
    )
    assert second is None
