"""LE1-C: turn manager units + replay edge cases 1, 2, 4, 5, 6, 14, 27.

Cancel latency is asserted in *virtual* time here (the harness is
synchronous); real winsound stop latency is a Windows-bench item, and the
player's 20 ms cancel poll is covered in tests/test_handsfree.py style
fakes. Nothing in this file claims a wall-clock measurement.
"""

import pytest
from harness import LiveDriver

from vox.engine.clock import VirtualClock
from vox.engine.timeline import Timeline
from vox.engine.turns import (
    CancelResult,
    CommitGuard,
    PostCommitKind,
    SpeculationViolation,
    StaleTurnError,
    TurnManager,
    TurnState,
)


def mapping_llm(table):
    return lambda utterance: table.get(utterance)


# -- unit-level manager behaviour -------------------------------------------


def test_generation_token_invalidated_by_cancel():
    clock = VirtualClock()
    manager = TurnManager(Timeline(clock), clock)
    turn = manager.open_turn("wake")
    token = manager.token(turn)
    assert manager.is_current(token)
    assert manager.cancel(turn, "user_stop") is CancelResult.FREE
    assert not manager.is_current(token)
    with pytest.raises(StaleTurnError):
        CommitGuard(manager).dispatch(token, side_effecting=False, run=lambda: "x")


def test_guard_blocks_side_effects_before_commit_point():
    clock = VirtualClock()
    manager = TurnManager(Timeline(clock), clock)
    turn = manager.open_turn("wake")
    guard = CommitGuard(manager)
    token = manager.token(turn)
    with pytest.raises(SpeculationViolation):
        guard.dispatch(token, side_effecting=True, run=lambda: "boom")
    assert guard.dispatch(token, side_effecting=False, run=lambda: "snapshot") == "snapshot"
    manager.add_fragment(turn, "open calculator")
    manager.hard_end(turn)
    assert guard.dispatch(token, side_effecting=True, run=lambda: "done") == "done"
    assert turn.committed and turn.state is TurnState.EXECUTING
    assert manager.cancel(turn, "stop") is CancelResult.AFTER_COMMIT


def test_rapid_fire_turns_queue_fifo():
    clock = VirtualClock()
    manager = TurnManager(Timeline(clock), clock)
    first = manager.open_turn("wake")
    second = manager.open_turn("followup")
    third = manager.open_turn("followup")
    assert [turn.id for turn in manager.queued] == [second.id, third.id]
    manager.close(first)
    assert manager.active is second and second.state is TurnState.LISTENING
    manager.close(second)
    assert manager.active is third


def test_cancelled_queued_turn_is_never_activated():
    clock = VirtualClock()
    manager = TurnManager(Timeline(clock), clock)
    first = manager.open_turn("wake")
    second = manager.open_turn("followup")
    third = manager.open_turn("followup")
    manager.cancel(second, "changed_mind")
    assert [turn.id for turn in manager.queued] == [third.id]
    manager.close(first)
    assert manager.active is third


def test_post_commit_classification():
    clock = VirtualClock()
    manager = TurnManager(Timeline(clock), clock)
    assert manager.classify_post_commit("stop") is PostCommitKind.STOP
    assert manager.classify_post_commit("what are you doing") is PostCommitKind.STATUS
    assert manager.classify_post_commit("no I meant edge") is PostCommitKind.CORRECTION
    assert manager.classify_post_commit("open notepad too") is PostCommitKind.NEW


# -- replay edge cases --------------------------------------------------------


def test_edge1_command_split_across_pause_is_one_turn_one_execution():
    driver = LiveDriver(mapping_llm({"open chrome and search for lofi": ("open_app", True)}))
    driver.start_turn()
    driver.partial("open chrome and")
    driver.tick(0.9)  # dangling: no soft/hard cut yet
    driver.partial("open chrome and search for lofi")
    driver.tick(0.3)  # soft end -> read-only speculation only
    driver.tick(0.3)  # hard end -> exactly one dispatch
    assert driver.tools.dispatched == [("list_windows", False), ("open_app", True)]
    finals = [e.text for e in driver.timeline.events() if e.kind == "final" and e.speaker == "user"]
    assert finals == ["open chrome and search for lofi"]


def test_edge2_trailing_off_is_not_cut_early():
    driver = LiveDriver(mapping_llm({"move this window to the right monitor": ("move", True)}))
    driver.start_turn()
    driver.partial("move this window to the")
    driver.tick(0.8)  # beyond complete hard-end, but partial dangles
    assert driver.tools.dispatched == []
    driver.partial("move this window to the right monitor")
    driver.tick(0.6)
    assert ("move", True) in driver.tools.dispatched


def test_edge4_barge_in_silences_tts_and_stores_only_spoken_part():
    driver = LiveDriver(
        mapping_llm({"open calculator": ("open_app", True), "open notepad": ("open_app", True)})
    )
    driver.start_turn()
    driver.say("open calculator")
    assert driver.tts.playing
    cancel_ms = driver.barge_in("open notepad")
    assert cancel_ms <= 150  # virtual time; see module docstring
    assert driver.tts.stop_calls == 1
    assistant = [
        e.text for e in driver.timeline.events() if e.speaker == "assistant" and e.kind == "final"
    ]
    assert assistant and len(assistant[0]) < len("open_app done.")  # truncated at offset
    assert driver.tools.dispatched.count(("open_app", True)) == 2


def test_edge5_speech_during_thinking_cancels_with_zero_stale_dispatch():
    driver = LiveDriver(mapping_llm({"open calculator": ("open_app", True)}))
    turn = driver.start_turn()
    driver.partial("open calculator")
    driver.tick(0.3)  # soft end: speculation only
    token = driver.manager.token(turn)
    driver.manager.cancel(turn, "user_spoke_again")
    with pytest.raises(StaleTurnError):
        driver.guard.dispatch(token, side_effecting=True, run=lambda: "stale")
    assert driver.tools.dispatched == [("list_windows", False)]  # read-only only


def test_edge6_post_commit_stop_causes_no_double_execution():
    driver = LiveDriver(mapping_llm({"open calculator": ("open_app", True)}))
    driver.start_turn()
    driver.say("open calculator")
    assert driver.tools.dispatched.count(("open_app", True)) == 1
    assert driver.post_commit_speech("stop") is PostCommitKind.STOP
    assert driver.turn is None
    assert driver.tools.dispatched.count(("open_app", True)) == 1


def test_edge14_rapid_fire_commands_run_in_order():
    driver = LiveDriver(
        mapping_llm(
            {
                "volume up": ("volume_up", True),
                "mute": ("mute", True),
            }
        )
    )
    driver.start_turn()
    driver.say("volume up")
    driver.finish_speaking()
    driver.start_turn(trigger="followup")
    driver.say("volume up")
    driver.finish_speaking()
    driver.start_turn(trigger="followup")
    driver.say("mute")
    side_effects = [name for name, side in driver.tools.dispatched if side]
    assert side_effects == ["volume_up", "volume_up", "mute"]


def test_edge27_no_side_effecting_dispatch_before_commit_across_flow():
    driver = LiveDriver(mapping_llm({"open calculator": ("open_app", True)}))
    driver.start_turn()
    driver.partial("open calc")
    driver.tick(0.3)  # soft end
    pre_commit = list(driver.tools.dispatched)
    assert all(not side for _name, side in pre_commit)
    driver.partial("open calculator")
    driver.tick(0.6)  # hard end -> commit -> dispatch
    assert ("open_app", True) in driver.tools.dispatched
