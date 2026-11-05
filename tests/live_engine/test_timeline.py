"""LE1-A: timeline ordering, typed events, clocks, engine settings."""

import pytest

from vox.engine import EngineMode, Timeline, VirtualClock, load_settings
from vox.events import LatencySample, ToolFinished, ToolStarted, TurnOpened


def test_timeline_orders_and_timestamps_from_injected_clock():
    clock = VirtualClock()
    timeline = Timeline(clock)
    first = timeline.append("user", "partial", "open", turn_id="t1")
    clock.advance(0.4)
    second = timeline.append("user", "final", "open calculator", turn_id="t1")
    assert (first.id, second.id) == (1, 2)
    assert second.t_mono - first.t_mono == pytest.approx(0.4)
    assert [event.text for event in timeline.events("t1")] == ["open", "open calculator"]
    assert timeline.events("other") == []


def test_timeline_ring_buffer_trims_but_ids_stay_monotonic():
    timeline = Timeline(VirtualClock(), max_events=3)
    for index in range(5):
        timeline.append("user", "partial", str(index))
    assert len(timeline) == 3
    assert [event.id for event in timeline.events()] == [3, 4, 5]
    assert [event.text for event in timeline.last(2)] == ["3", "4"]
    assert timeline.last(0) == []


def test_append_event_maps_tool_and_system_kinds():
    timeline = Timeline(VirtualClock())
    timeline.append_event(TurnOpened(turn_id="t1", trigger="wake"), turn_id="t1")
    started = timeline.append_event(ToolStarted(name="open_app", title="Open"), turn_id="t1")
    finished = timeline.append_event(
        ToolFinished(name="open_app", ok=True, evidence_summary="opened"), turn_id="t1"
    )
    sample = timeline.append_event(
        LatencySample(turn_id="t1", stage="dispatch", ms=12.5), turn_id="t1"
    )
    assert (started.speaker, started.kind) == ("tool", "tool_started")
    assert (finished.speaker, finished.kind) == ("tool", "tool_finished")
    assert (sample.speaker, sample.kind) == ("system", "state_note")
    assert isinstance(timeline.events()[0].event, TurnOpened)


def test_clear_forgets_conversation():
    timeline = Timeline(VirtualClock())
    timeline.append("user", "final", "secret words")
    timeline.clear()
    assert len(timeline) == 0
    assert timeline.events() == []


def test_virtual_clock_rejects_backwards_travel():
    clock = VirtualClock()
    try:
        clock.advance(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_settings_default_legacy_and_env_parsing():
    assert load_settings({}).mode is EngineMode.LEGACY
    assert load_settings({"VOX_ENGINE_MODE": "live"}).mode is EngineMode.LIVE
    assert load_settings({"VOX_ENGINE_MODE": "nonsense"}).mode is EngineMode.LEGACY
