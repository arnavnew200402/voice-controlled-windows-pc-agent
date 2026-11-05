"""Two-stage "Hi Vox" wake detection + session state machine (spec 4.0).

Stage 0/1 (cheap, high recall): an RMS/VAD gate decides whether a frame is
worth decoding, and a phrase match on a *partial* snippet raises the soft
Listening state. Stage 2 (verify): a *final* snippet must still contain
the phrase and clear the sensitivity's word-confidence bar; alias matches
with low confidence are rejected (a clearly-spoken "hi box" at high
confidence still wakes — that is what the alias set is for). Everything is
local; nothing leaves the process from this module. The wake phrase is a
doorbell: it opens a turn with ``trigger=wake`` and carries no trust.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from vox.engine.clock import Clock, SystemClock
from vox.engine.config import WakeSettings
from vox.engine.endpointing import PreRollBuffer
from vox.engine.timeline import Timeline
from vox.engine.turns import Turn, TurnManager
from vox.events import WakeDetected, WakeTimeout, WakeVerified
from vox.voice.audio import frame_rms
from vox.voice.wake import ScoredWakeEngine, contains_wake_phrase

VERIFY_WINDOW_S = 2.5


@dataclass(frozen=True)
class WakeStep:
    kind: Literal["detected", "verified", "rejected"]
    phrase: str = ""
    score: float = 0.0
    reason: str = ""
    ms: float = 0.0


class TwoStageWake:
    def __init__(
        self,
        engine: ScoredWakeEngine,
        settings: WakeSettings,
        clock: Clock | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._sets = settings.phrase_sets()
        self._clock = clock or SystemClock()
        self._pending_since: float | None = None
        self._pending_phrase = ""
        self.frames_seen = 0
        self.gate_skipped = 0
        self.last_detect_at: float | None = None
        self.last_verified_text = ""

    def feed(self, frame: bytes, rms: float) -> list[WakeStep]:
        self.frames_seen += 1
        now = self._clock.monotonic()
        steps: list[WakeStep] = []
        if self._pending_since is not None and now - self._pending_since > VERIFY_WINDOW_S:
            steps.append(
                WakeStep(
                    "rejected",
                    phrase=self._pending_phrase,
                    reason="verify_timeout",
                    ms=(now - self._pending_since) * 1000.0,
                )
            )
            self._pending_since = None
        if self._pending_since is None and rms < self._settings.gate_rms:
            self.gate_skipped += 1
            return steps
        snippet = self._engine.feed_scored(frame)
        if snippet is None or not contains_wake_phrase(snippet.text, **self._sets):  # type: ignore[arg-type]
            return steps
        if not snippet.final:
            if self._pending_since is not None:
                self._pending_since = now  # phrase still on the partials: stay pending
            if self._pending_since is None:
                self._pending_since = now
                self._pending_phrase = snippet.text
                self.last_detect_at = now
                steps.append(WakeStep("detected", phrase=snippet.text, score=rms))
            return steps
        # Final snippet: stage-2 verification.
        was_pending = self._pending_since is not None
        detect_at = self._pending_since if was_pending else now
        if not was_pending:
            self.last_detect_at = now
            steps.append(WakeStep("detected", phrase=snippet.text, score=rms))
        self._pending_since = None
        latency_ms = (now - (detect_at or now)) * 1000.0
        if snippet.confidence is not None and snippet.confidence < self._settings.min_confidence:
            steps.append(
                WakeStep("rejected", phrase=snippet.text, reason="low_confidence", ms=latency_ms)
            )
            return steps
        self._engine.reset()
        self.last_verified_text = snippet.text
        steps.append(
            WakeStep(
                "verified",
                phrase=snippet.text,
                score=snippet.confidence if snippet.confidence is not None else 1.0,
                ms=latency_ms,
            )
        )
        return steps


class WakeSessionState(StrEnum):
    IDLE = "idle"
    SOFT_LISTENING = "soft_listening"
    LISTENING = "listening"
    SUSPENDED = "suspended"


class WakeSession:
    """Owns wake state: idle → soft → listening(turn open) → idle.

    Suspended (locked session, mic muted/busy, setting off) guarantees
    zero activations: frames are dropped before the spotter. While the
    assistant itself is speaking the detector is deaf (half-duplex; edge
    case 32 documented behaviour until an AEC exists).
    """

    def __init__(
        self,
        spotter: TwoStageWake,
        manager: TurnManager,
        timeline: Timeline,
        clock: Clock | None = None,
        *,
        settings: WakeSettings,
        preroll: PreRollBuffer | None = None,
    ) -> None:
        self._spotter = spotter
        self._manager = manager
        self._timeline = timeline
        self._clock = clock or SystemClock()
        self._settings = settings
        self._preroll = preroll or PreRollBuffer(self._clock)
        self._state = WakeSessionState.IDLE
        self._suspended = False
        self._speaking = False
        self._loopback = False
        self._listening_since: float | None = None
        self._speech_started = False
        self.turn: Turn | None = None
        self.command_audio = b""

    @property
    def state(self) -> WakeSessionState:
        if self._suspended or not self._settings.enabled:
            return WakeSessionState.SUSPENDED
        return self._state

    @property
    def indicator(self) -> Literal["wake_listening", "active_listening", "off"]:
        state = self.state
        if state is WakeSessionState.LISTENING:
            return "active_listening"
        if state in {WakeSessionState.IDLE, WakeSessionState.SOFT_LISTENING}:
            return "wake_listening"
        return "off"

    def suspend(self, reason: str) -> None:
        del reason  # recorded by callers' logs; state is what matters here
        self._suspended = True

    def resume(self) -> None:
        self._suspended = False

    def set_speaking(self, speaking: bool) -> None:
        self._speaking = speaking

    def set_loopback(self, active: bool) -> None:
        """Loopback correlation stub: own TTS / media audio is playing."""
        self._loopback = active

    def note_speech_started(self) -> None:
        self._speech_started = True

    def complete_turn(self) -> None:
        """Pipeline finished the wake-opened turn: return to wake idle."""
        self.turn = None
        self._listening_since = None
        self._speech_started = False
        self._state = WakeSessionState.IDLE
        self.command_audio = b""

    def feed(self, frame: bytes) -> None:
        if not self._settings.enabled or self._suspended:
            return
        self._preroll.push(frame)
        if self._speaking:
            return  # half-duplex: deaf during own speech
        now = self._clock.monotonic()
        steps = (
            []
            if self._state is WakeSessionState.LISTENING
            else self._spotter.feed(frame, frame_rms(frame))
        )
        for step in steps:
            if step.kind == "detected":
                self._state = WakeSessionState.SOFT_LISTENING
                self._timeline.append_event(
                    WakeDetected(stage1_score=step.score, phrase=step.phrase)
                )
            elif step.kind == "verified":
                if self._loopback:
                    self._timeline.append_event(
                        WakeVerified(ok=False, reason="loopback", ms=step.ms)
                    )
                    self._state = WakeSessionState.IDLE
                    continue
                self._timeline.append_event(WakeVerified(ok=True, reason="", ms=step.ms))
                self.turn = self._manager.open_turn("wake")
                self._state = WakeSessionState.LISTENING
                self._listening_since = now
                self._speech_started = False
                since = self._spotter.last_detect_at or now
                self.command_audio = self._preroll.audio_from(since)
            else:  # rejected: silent revert, audio discarded
                self._timeline.append_event(WakeVerified(ok=False, reason=step.reason, ms=step.ms))
                self._state = WakeSessionState.IDLE
        if (
            self._state is WakeSessionState.LISTENING
            and self._listening_since is not None
            and not self._speech_started
            and now - self._listening_since > self._settings.listen_timeout_s
        ):
            self._timeline.append_event(WakeTimeout())
            if self.turn is not None:
                self._manager.cancel(self.turn, "wake_timeout")
                self.turn = None
            self._state = WakeSessionState.IDLE
            self._listening_since = None


def calibrate_offset(
    noise_rms: Sequence[float], phrase_rms: Sequence[float], *, base_gate: float
) -> float:
    """Per-user gate offset from the Calibrate wizard's samples.

    Places the stage-0 gate midway between the noise floor's high end and
    the spoken phrase's low end; clamped so a bad calibration can never
    deafen or hypersensitise the detector. Only numbers are stored.
    """
    if not noise_rms or not phrase_rms:
        return 0.0
    noise_high = statistics.quantiles(noise_rms, n=20)[18] if len(noise_rms) > 1 else noise_rms[0]
    phrase_low = statistics.quantiles(phrase_rms, n=10)[0] if len(phrase_rms) > 1 else phrase_rms[0]
    target = (noise_high + phrase_low) / 2
    return max(-0.02, min(0.05, target - base_gate))
