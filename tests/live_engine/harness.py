"""Virtual-clock replay harness for the Live Command Engine (spec §6).

Drives the *real* Timeline/TurnManager/Endpointer/Control/CommitGuard with
scripted STT partials, a scripted fake LLM (utterance -> tool dict), fake
tools that record every dispatch, and a fake TTS with scripted spoken
offsets. The shipped pipeline (LE4) will reuse the same components with
real providers; this driver exists so turn-taking behaviour is provable
without a microphone, network, or Windows desktop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from vox.engine.clock import VirtualClock
from vox.engine.config import EngineSettings
from vox.engine.control import classify_control
from vox.engine.endpointing import Decision, Endpointer
from vox.engine.timeline import Timeline
from vox.engine.turns import CommitGuard, PostCommitKind, Turn, TurnManager, TurnState

# utterance -> (tool name, side_effecting) or None for "no tool"
FakeLLM = Callable[[str], tuple[str, bool] | None]


class FakeScoredEngine:
    """Queue-scripted ScoredWakeEngine for wake replay scenarios (LE1b)."""

    def __init__(self, snippets: list) -> None:
        self._snippets = list(snippets)
        self.resets = 0
        self.fed = 0

    def feed_scored(self, frame: bytes):
        self.fed += 1
        return self._snippets.pop(0) if self._snippets else None

    def reset(self) -> None:
        self.resets += 1


def frame(sample: int = 8000, samples: int = 4000) -> bytes:
    """One 250 ms int16 frame at a constant sample value (RMS control)."""
    return int(sample).to_bytes(2, "little", signed=True) * samples


@dataclass
class FakeTools:
    dispatched: list[tuple[str, bool]] = field(default_factory=list)  # (name, side_effecting)
    snapshot_calls: int = 0

    def run(self, name: str, side_effecting: bool) -> str:
        self.dispatched.append((name, side_effecting))
        if not side_effecting:
            self.snapshot_calls += 1
        return f"{name} done."


class FakeTTS:
    """Scripted player: stop() reports the first ``spoken_ratio`` of text."""

    def __init__(self, spoken_ratio: float = 0.4) -> None:
        self.spoken_ratio = spoken_ratio
        self.playing = False
        self.text = ""
        self.stop_calls = 0

    def play(self, text: str) -> None:
        self.text = text
        self.playing = True

    def stop(self) -> str:
        self.stop_calls += 1
        self.playing = False
        cut = int(len(self.text) * self.spoken_ratio)
        spoken = self.text[:cut]
        return spoken.rsplit(" ", 1)[0] if 0 < cut < len(self.text) and " " in spoken else spoken

    def finish(self) -> str:
        self.playing = False
        return self.text


class LiveDriver:
    """Minimal reference pipeline: partials -> endpointing -> guard -> TTS."""

    def __init__(self, llm: FakeLLM, settings: EngineSettings | None = None) -> None:
        self.clock = VirtualClock()
        self.settings = settings or EngineSettings()
        self.timeline = Timeline(self.clock)
        self.manager = TurnManager(self.timeline, self.clock, self.settings)
        self.guard = CommitGuard(self.manager)
        self.endpointer = Endpointer(self.settings)
        self.tools = FakeTools()
        self.tts = FakeTTS()
        self.llm = llm
        self.speculations: list[str] = []
        self.turn: Turn | None = None

    # -- input side ---------------------------------------------------------

    def start_turn(self, trigger: str = "wake") -> Turn:
        self.turn = self.manager.open_turn(trigger)
        self.endpointer.reset(self.clock.monotonic())
        return self.turn

    def partial(self, text: str) -> None:
        assert self.turn is not None
        self.endpointer.on_partial(text, self.clock.monotonic())
        self.manager.note_partial(self.turn, text)

    def tick(self, seconds: float) -> Decision:
        """Advance virtual time; run endpointing + downstream pipeline."""
        self.clock.advance(seconds)
        assert self.turn is not None
        decision = self.endpointer.poll(self.clock.monotonic())
        if self.endpointer.consume_resumed():
            self.manager.resume(self.turn)
            self.speculations.clear()  # speculative work discarded on resume
        if decision is Decision.SOFT_END:
            self.manager.soft_end(self.turn)
            token = self.manager.token(self.turn)
            self.speculations.append(
                self.guard.dispatch(
                    token,
                    side_effecting=False,  # whitelist: read-only snapshot
                    run=lambda: self.tools.run("list_windows", False),
                )
            )
        elif decision is Decision.HARD_END:
            self._finalise_turn(self.endpointer.partial)
        return decision

    def say(self, text: str, *, settle: float = 0.6) -> None:
        """One full utterance: partial now, silence until it finalises."""
        self.partial(text)
        self.tick(settle)

    # -- downstream ---------------------------------------------------------

    def _finalise_turn(self, transcript: str) -> None:
        assert self.turn is not None
        turn = self.turn
        self.manager.add_fragment(turn, transcript)
        utterance = self.manager.hard_end(turn)
        control = classify_control(utterance, approval_pending=False)
        if control is not None:
            self.manager.cancel(turn, f"control:{control.action}")
            self.turn = None
            return
        token = self.manager.token(turn)
        planned = self.llm(utterance)
        if planned is None:
            self.manager.close(turn)
            self.turn = None
            return
        name, side_effecting = planned
        evidence = self.guard.dispatch(
            token,
            side_effecting=side_effecting,
            run=lambda: self.tools.run(name, side_effecting),
        )
        self.manager.begin_speaking(turn)
        self.tts.play(evidence)

    def finish_speaking(self) -> None:
        assert self.turn is not None
        self.manager.record_assistant_speech(self.turn, self.tts.finish())
        self.manager.close(self.turn)
        self.turn = self.manager.active  # next queued turn, if any

    def barge_in(self, new_text: str) -> float:
        """User speaks over TTS. Returns virtual ms until TTS was silent."""
        assert self.turn is not None and self.turn.state is TurnState.SPEAKING
        started = self.clock.monotonic()
        spoken = self.tts.stop()  # same virtual instant: driver is synchronous
        silent_at = self.clock.monotonic()
        self.manager.record_assistant_speech(self.turn, spoken)
        self.manager.cancel(self.turn, "barge_in")
        self.start_turn(trigger="followup")
        self.say(new_text)
        return (silent_at - started) * 1000.0

    def post_commit_speech(self, text: str) -> PostCommitKind:
        kind = self.manager.classify_post_commit(text)
        if kind is PostCommitKind.STOP and self.turn is not None:
            self.tts.stop()
            self.manager.cancel(self.turn, "stop_word")
            self.turn = None
        return kind
