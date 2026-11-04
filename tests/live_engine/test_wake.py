"""LE1b: wake settings/phrase config (two-stage session tests follow)."""

from vox.engine.config import WakeSensitivity, WakeSettings
from vox.engine.i18n import WAKE_GREETINGS
from vox.voice.wake import contains_wake_phrase, strip_wake_tokens


def test_wake_i18n_parity():
    assert set(WAKE_GREETINGS) == {"en", "hi"}
    for table in WAKE_GREETINGS.values():
        assert set(table) == {"strong", "weak"} and all(table.values())


def test_phrase_sets_default_accept_hi_and_hey_not_ok():
    sets = WakeSettings(enabled=True).phrase_sets()
    assert contains_wake_phrase("hi vox", **sets)
    assert contains_wake_phrase("hey vox", **sets)
    assert contains_wake_phrase("hai vox", **sets)
    assert contains_wake_phrase("हाय वॉक्स", **sets)
    assert not contains_wake_phrase("okay vox", **sets)  # not a configured greeting
    assert not contains_wake_phrase("hi folks", **sets)  # media greeting, excluded
    assert strip_wake_tokens("hai vox open chrome", **sets) == "open chrome"


def test_custom_name_uses_exact_name_only():
    settings = WakeSettings(enabled=True, name="Jarvis")
    sets = settings.phrase_sets()
    assert settings.uses_custom_name
    assert contains_wake_phrase("hi jarvis", **sets)
    assert not contains_wake_phrase("hi vox", **sets)
    assert not contains_wake_phrase("hi box", **sets)  # no variants for custom names


def test_sensitivity_presets_and_calibration_offset():
    balanced = WakeSettings()
    assert balanced.gate_rms == 0.03 and balanced.min_confidence == 0.7
    assert WakeSettings(sensitivity=WakeSensitivity.HIGH).gate_rms < balanced.gate_rms
    assert WakeSettings(sensitivity=WakeSensitivity.LOW).min_confidence > balanced.min_confidence
    assert WakeSettings(calibration_offset=0.02).gate_rms == 0.05


# -- two-stage session: edge cases 29-36 (virtual time; see SPEECH_BENCH) --

from harness import FakeScoredEngine, frame

from vox.engine.clock import VirtualClock
from vox.engine.endpointing import PreRollBuffer
from vox.engine.timeline import Timeline
from vox.engine.turns import TurnManager, TurnState
from vox.engine.wake import TwoStageWake, WakeSession, WakeSessionState, calibrate_offset
from vox.events import WakeDetected, WakeTimeout, WakeVerified
from vox.voice.wake import ScoredSnippet

LOUD = frame(8000)  # RMS ~0.24, above every gate preset
QUIET = frame(50)  # RMS ~0.0015, below the gate


def make_session(snippets, settings=None):
    clock = VirtualClock()
    timeline = Timeline(clock)
    manager = TurnManager(timeline, clock)
    settings = settings or WakeSettings(enabled=True)
    engine = FakeScoredEngine(snippets)
    spotter = TwoStageWake(engine, settings, clock)
    session = WakeSession(
        spotter, manager, timeline, clock, settings=settings, preroll=PreRollBuffer(clock)
    )
    return session, clock, timeline, manager, engine, spotter


def snippet(text, *, final, conf=None):
    return ScoredSnippet(text=text, final=final, confidence=conf)


def events_of(timeline, kind):
    return [e.event for e in timeline.events() if isinstance(e.event, kind)]


def test_edge29_wake_alone_listens_then_times_out_silently():
    session, clock, timeline, _manager, _engine, _spotter = make_session(
        [snippet("hi vox", final=False), snippet("hi vox", final=True, conf=0.95)]
    )
    started = clock.monotonic()
    session.feed(LOUD)
    assert session.state is WakeSessionState.SOFT_LISTENING
    assert session.indicator == "wake_listening"
    assert (clock.monotonic() - started) * 1000 <= 150  # virtual: same tick
    session.feed(LOUD)
    assert session.state is WakeSessionState.LISTENING
    assert session.indicator == "active_listening"
    assert session.turn is not None and session.turn.trigger == "wake"
    for _ in range(30):  # >6 s of quiet frames
        clock.advance(0.25)
        session.feed(QUIET)
    assert session.state is WakeSessionState.IDLE
    assert session.turn is None
    assert len(events_of(timeline, WakeTimeout)) == 1
    assert not [e for e in timeline.events() if e.kind == "tool_started"]


def test_edge30_one_breath_keeps_preroll_and_strips_wake_tokens():
    session, _clock, _timeline, _manager, _engine, spotter = make_session(
        [
            snippet("hi vox open chr", final=False),
            snippet("hi vox open chrome", final=True, conf=0.95),
        ]
    )
    session.feed(LOUD)
    session.feed(LOUD)
    assert session.state is WakeSessionState.LISTENING
    assert spotter.last_verified_text == "hi vox open chrome"
    assert strip_wake_tokens(spotter.last_verified_text) == "open chrome"
    assert len(session.command_audio) >= len(LOUD)  # audio from detection onward kept


def test_edge31_near_misses_and_loopback_do_not_activate():
    # Weak greeting + alias name never even detects.
    session, *_rest = make_session([snippet("high fox", final=True, conf=0.99)])
    session.feed(LOUD)
    assert session.state is WakeSessionState.IDLE and session.turn is None
    # Alias at low stage-2 confidence is rejected.
    session, _clock, timeline, *_rest = make_session(
        [snippet("hi box", final=False), snippet("hi box", final=True, conf=0.4)]
    )
    session.feed(LOUD)
    session.feed(LOUD)
    assert session.state is WakeSessionState.IDLE and session.turn is None
    assert events_of(timeline, WakeVerified)[-1].reason == "low_confidence"
    # The same audio arriving over loopback (media/TTS) is rejected.
    session, _clock, timeline, *_rest = make_session(
        [snippet("hi vox", final=False), snippet("hi vox", final=True, conf=0.99)]
    )
    session.set_loopback(True)
    session.feed(LOUD)
    session.feed(LOUD)
    assert session.turn is None
    assert events_of(timeline, WakeVerified)[-1].reason == "loopback"


def test_edge32_deaf_during_own_speech_half_duplex():
    session, _clock, _timeline, _manager, engine, _spotter = make_session(
        [snippet("hi vox", final=False), snippet("hi vox", final=True, conf=0.99)]
    )
    session.set_speaking(True)
    session.feed(LOUD)
    session.feed(LOUD)
    assert session.state is WakeSessionState.IDLE
    assert engine.fed == 0  # spotter never saw the frames
    session.set_speaking(False)
    session.feed(LOUD)
    session.feed(LOUD)
    assert session.state is WakeSessionState.LISTENING


def test_edge34_wake_carries_trigger_and_never_approves():
    from vox.engine.control import ControlAction, classify_control

    session, _clock, timeline, _manager, _engine, _spotter = make_session(
        [snippet("hi vox yes", final=True, conf=0.99)]
    )
    session.feed(LOUD)
    assert session.turn is not None and session.turn.trigger == "wake"
    sources = [e for e in timeline.events() if e.kind == "state_note"]
    assert any(
        getattr(e.event, "type", "") == "trigger_source" and e.event.source == "wake"
        for e in sources
    )
    # "yes" after a wake is only ever a classification; nothing in the wake
    # path resolves an approval (click-approval policy unchanged).
    assert classify_control("yes", approval_pending=True).action is ControlAction.APPROVE
    assert not [e for e in timeline.events() if e.kind == "approval"]
    assert session.turn.state is TurnState.LISTENING


def test_edge35_suspended_or_disabled_never_activates():
    session, _clock, timeline, _manager, engine, _spotter = make_session(
        [snippet("hi vox", final=True, conf=0.99)]
    )
    session.suspend("session_locked")
    before = len(timeline)
    session.feed(LOUD)
    assert session.state is WakeSessionState.SUSPENDED
    assert session.indicator == "off"
    assert len(timeline) == before and engine.fed == 0
    session.resume()
    assert session.indicator == "wake_listening"
    disabled, *_rest = make_session(
        [snippet("hi vox", final=True, conf=0.99)], settings=WakeSettings(enabled=False)
    )
    disabled.feed(LOUD)
    assert disabled.state is WakeSessionState.SUSPENDED and disabled.turn is None


def test_edge36_stage2_reject_reverts_silently_within_window():
    session, clock, timeline, _manager, _engine, _spotter = make_session(
        [snippet("hi vox", final=False), snippet("hi vox", final=True, conf=0.3)]
    )
    session.feed(LOUD)
    assert session.state is WakeSessionState.SOFT_LISTENING
    clock.advance(0.3)
    session.feed(LOUD)
    assert session.state is WakeSessionState.IDLE
    assert _manager.active is None
    verified = events_of(timeline, WakeVerified)
    assert verified and verified[-1].ok is False and verified[-1].ms <= 400
    assert len(events_of(timeline, WakeDetected)) == 1


def test_listening_session_does_not_retrigger_on_command_frames():
    session, _clock, timeline, *_rest = make_session(
        [
            snippet("hi vox", final=True, conf=0.99),
            snippet("hi vox", final=True, conf=0.99),  # would re-verify if fed
        ]
    )
    session.feed(LOUD)
    first_turn = session.turn
    session.feed(LOUD)  # command-phase frame: spotter must not be fed
    assert session.turn is first_turn
    assert len(events_of(timeline, WakeVerified)) == 1
    session.complete_turn()
    assert session.state is WakeSessionState.IDLE


def test_gate_skips_quiet_frames_and_calibrate_offset():
    session, _clock, _timeline, _manager, engine, spotter = make_session([])
    for _ in range(10):
        session.feed(QUIET)
    assert spotter.gate_skipped == 10 and engine.fed == 0
    assert calibrate_offset([], [0.2], base_gate=0.03) == 0.0
    offset = calibrate_offset([0.01] * 20, [0.2] * 10, base_gate=0.03)
    assert 0.0 < offset <= 0.05
