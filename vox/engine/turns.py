"""Turn manager: generations, fragments, the commit point (spec 4.2).

The commit point is the first dispatch of a side-effecting tool. Before it,
cancellation is free and instant (generation bump invalidates every token).
After it, new speech is classified (stop / correction / status / new) and
never silently abandons a half-run effect. :class:`CommitGuard` makes the
speculation whitelist (4.6) enforceable: read-only dispatch is allowed for
any current turn; side-effecting dispatch only from the processing state
onward, and the first one moves the turn past the commit point.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, TypeVar, cast

from vox.engine.clock import Clock, SystemClock
from vox.engine.config import EngineSettings
from vox.engine.control import ControlAction, classify_control
from vox.engine.endpointing import tokens
from vox.engine.timeline import Timeline
from vox.events import Endpointing, LatencySample, TriggerSource, TurnCancelled, TurnOpened

T = TypeVar("T")

TriggerName = Literal["hotkey", "wake", "followup", "typed"]


class TurnState(StrEnum):
    QUEUED = "queued"
    LISTENING = "listening"
    SOFT_ENDED = "soft_ended"
    PROCESSING = "processing"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CancelResult(StrEnum):
    FREE = "free"  # before the commit point: nothing had side effects
    AFTER_COMMIT = "after_commit"


class PostCommitKind(StrEnum):
    STOP = "stop"
    CORRECTION = "correction"
    STATUS = "status"
    NEW = "new"


class StaleTurnError(RuntimeError):
    """A tool call arrived for a cancelled/replaced turn generation."""


class SpeculationViolation(RuntimeError):
    """A side-effecting tool was dispatched before the commit point."""


@dataclass(frozen=True)
class GenerationToken:
    turn_id: str
    generation: int


@dataclass
class Turn:
    id: str
    trigger: str
    generation: int = 1
    state: TurnState = TurnState.LISTENING
    fragments: list[str] = field(default_factory=list)
    merged_from: list[str] = field(default_factory=list)
    opened_at: float = 0.0
    committed: bool = False
    committed_at: float | None = None

    @property
    def text(self) -> str:
        return " ".join(fragment for fragment in self.fragments if fragment)


_CORRECTION_PREFIXES = {"no", "not", "nahi", "nahin", "नहीं"}
_CORRECTION_PHRASES = ("i meant", "i said", "mera matlab", "मेरा मतलब")


class TurnManager:
    def __init__(
        self,
        timeline: Timeline,
        clock: Clock | None = None,
        settings: EngineSettings | None = None,
    ) -> None:
        self._timeline = timeline
        self._clock = clock or SystemClock()
        self._settings = settings or EngineSettings()
        self._sequence = 0
        self._turns: dict[str, Turn] = {}
        self._active: Turn | None = None
        self._queue: deque[Turn] = deque()

    # -- lifecycle ---------------------------------------------------------

    def open_turn(self, trigger: str) -> Turn:
        self._sequence += 1
        turn = Turn(id=f"turn-{self._sequence}", trigger=trigger, opened_at=self._clock.monotonic())
        self._turns[turn.id] = turn
        if self._active is None:
            self._activate(turn)
        else:
            turn.state = TurnState.QUEUED
            self._queue.append(turn)
        known = trigger in {"hotkey", "wake", "followup", "typed"}
        self._timeline.append_event(
            TurnOpened(turn_id=turn.id, trigger=cast(TriggerName, trigger) if known else "test"),
            turn_id=turn.id,
        )
        if known:
            self._timeline.append_event(
                TriggerSource(turn_id=turn.id, source=cast(TriggerName, trigger)),
                turn_id=turn.id,
            )
        return turn

    def _activate(self, turn: Turn) -> None:
        turn.state = TurnState.LISTENING
        self._active = turn

    @property
    def active(self) -> Turn | None:
        return self._active

    @property
    def queued(self) -> list[Turn]:
        return list(self._queue)

    def get(self, turn_id: str) -> Turn:
        return self._turns[turn_id]

    # -- speech intake -----------------------------------------------------

    def note_partial(self, turn: Turn, text: str, asr_confidence: float | None = None) -> None:
        self._timeline.append(
            "user", "partial", text, turn_id=turn.id, asr_confidence=asr_confidence
        )

    def add_fragment(self, turn: Turn, text: str, asr_confidence: float | None = None) -> str:
        cleaned = " ".join(text.split())
        if cleaned:
            turn.fragments.append(cleaned)
            self._timeline.append(
                "user", "final", cleaned, turn_id=turn.id, asr_confidence=asr_confidence
            )
        return turn.text

    def soft_end(self, turn: Turn) -> None:
        if turn.state is TurnState.LISTENING:
            turn.state = TurnState.SOFT_ENDED
            self._timeline.append_event(Endpointing(level="soft", turn_id=turn.id), turn_id=turn.id)
            self._latency(turn, "soft_end")

    def resume(self, turn: Turn) -> None:
        if turn.state is TurnState.SOFT_ENDED:
            turn.state = TurnState.LISTENING

    def hard_end(self, turn: Turn) -> str:
        turn.state = TurnState.PROCESSING
        self._timeline.append_event(Endpointing(level="hard", turn_id=turn.id), turn_id=turn.id)
        self._latency(turn, "hard_end")
        return turn.text

    # -- commit point & generations ---------------------------------------

    def token(self, turn: Turn) -> GenerationToken:
        return GenerationToken(turn_id=turn.id, generation=turn.generation)

    def is_current(self, token: GenerationToken) -> bool:
        turn = self._turns.get(token.turn_id)
        return (
            turn is not None
            and turn.generation == token.generation
            and turn.state not in {TurnState.CANCELLED, TurnState.CLOSED}
        )

    def mark_committed(self, turn: Turn) -> None:
        if not turn.committed:
            turn.committed = True
            turn.committed_at = self._clock.monotonic()
            turn.state = TurnState.EXECUTING
            self._latency(turn, "commit")

    def begin_speaking(self, turn: Turn) -> None:
        turn.state = TurnState.SPEAKING

    def record_assistant_speech(self, turn: Turn, spoken_text: str) -> None:
        """Store only what was actually spoken (post-interruption offset)."""
        if spoken_text:
            self._timeline.append("assistant", "final", spoken_text, turn_id=turn.id)

    def cancel(self, turn: Turn, reason: str) -> CancelResult:
        result = CancelResult.AFTER_COMMIT if turn.committed else CancelResult.FREE
        turn.generation += 1  # invalidate every outstanding token
        turn.state = TurnState.CANCELLED
        self._timeline.append_event(TurnCancelled(turn_id=turn.id, reason=reason), turn_id=turn.id)
        self._latency(turn, "cancel")
        self._dequeue(turn)
        self._promote(turn)
        return result

    def close(self, turn: Turn) -> None:
        turn.state = TurnState.CLOSED
        self._dequeue(turn)
        self._promote(turn)

    def _dequeue(self, turn: Turn) -> None:
        if turn in self._queue:
            self._queue.remove(turn)

    def _promote(self, finished: Turn) -> None:
        if self._active is finished:
            self._active = None
            if self._queue:
                self._activate(self._queue.popleft())

    # -- post-commit speech (provisional until LE2 contextualiser) --------

    def classify_post_commit(self, text: str, *, approval_pending: bool = False) -> PostCommitKind:
        control = classify_control(text, approval_pending=approval_pending)
        if control is not None:
            if control.action is ControlAction.STOP:
                return PostCommitKind.STOP
            if control.action is ControlAction.STATUS:
                return PostCommitKind.STATUS
        parts = tokens(text)
        lowered = " ".join(parts)
        if (parts and parts[0] in _CORRECTION_PREFIXES) or any(
            phrase in lowered for phrase in _CORRECTION_PHRASES
        ):
            return PostCommitKind.CORRECTION
        return PostCommitKind.NEW

    def _latency(self, turn: Turn, stage: str) -> None:
        ms = (self._clock.monotonic() - turn.opened_at) * 1000.0
        self._timeline.append_event(
            LatencySample(turn_id=turn.id, stage=stage, ms=ms), turn_id=turn.id
        )


class CommitGuard:
    """Dispatcher front-door enforcing generations + the speculation rules."""

    def __init__(self, manager: TurnManager) -> None:
        self._manager = manager

    def dispatch(self, token: GenerationToken, *, side_effecting: bool, run: Callable[[], T]) -> T:
        if not self._manager.is_current(token):
            raise StaleTurnError(f"stale generation for {token.turn_id}")
        turn = self._manager.get(token.turn_id)
        if side_effecting:
            if turn.state in {TurnState.LISTENING, TurnState.SOFT_ENDED, TurnState.QUEUED}:
                raise SpeculationViolation(
                    f"side-effecting dispatch before commit point in state {turn.state}"
                )
            self._manager.mark_committed(turn)
        return run()
