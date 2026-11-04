"""Ordered per-session timeline: everything said and done, one log.

The timeline extends the existing event ledger philosophy (``vox/events.py``)
rather than creating a second one: plain utterance/evidence records use the
§4.1 envelope, and typed engine events (endpointing, latency, wake, …) are
appended through :meth:`Timeline.append_event`. In-RAM only in LE1; LE3 adds
the SQLite checkpoint. Raw audio is never stored here.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from vox.engine.clock import Clock, SystemClock
from vox.events import (
    ApprovalRequested,
    ApprovalResolved,
    Event,
    ToolFinished,
    ToolStarted,
)

Speaker = Literal["user", "assistant", "ambient", "system", "tool"]
TimelineKind = Literal[
    "partial",
    "final",
    "tool_started",
    "tool_finished",
    "approval",
    "state_note",
    "screen_note",
    "note",
]


@dataclass(frozen=True)
class TimelineEvent:
    id: int
    turn_id: str | None
    t_mono: float
    t_wall: float
    speaker: Speaker
    kind: TimelineKind
    text: str = ""
    asr_confidence: float | None = None
    lang: str | None = None
    event: Event | None = None


_EVENT_KIND: dict[type[Event], tuple[Speaker, TimelineKind]] = {
    ToolStarted: ("tool", "tool_started"),
    ToolFinished: ("tool", "tool_finished"),
    ApprovalRequested: ("system", "approval"),
    ApprovalResolved: ("system", "approval"),
}


class Timeline:
    """Append-only ordered log with a bounded ring buffer."""

    def __init__(self, clock: Clock | None = None, max_events: int = 2000) -> None:
        self._clock = clock or SystemClock()
        self._events: deque[TimelineEvent] = deque(maxlen=max_events)
        self._next_id = 1

    def append(
        self,
        speaker: Speaker,
        kind: TimelineKind,
        text: str = "",
        *,
        turn_id: str | None = None,
        asr_confidence: float | None = None,
        lang: str | None = None,
        event: Event | None = None,
    ) -> TimelineEvent:
        record = TimelineEvent(
            id=self._next_id,
            turn_id=turn_id,
            t_mono=self._clock.monotonic(),
            t_wall=self._clock.wall(),
            speaker=speaker,
            kind=kind,
            text=text,
            asr_confidence=asr_confidence,
            lang=lang,
            event=event,
        )
        self._next_id += 1
        self._events.append(record)
        return record

    def append_event(self, event: Event, *, turn_id: str | None = None) -> TimelineEvent:
        speaker, kind = _EVENT_KIND.get(type(event), ("system", "state_note"))
        return self.append(speaker, kind, turn_id=turn_id, event=event)

    def events(self, turn_id: str | None = None) -> list[TimelineEvent]:
        if turn_id is None:
            return list(self._events)
        return [record for record in self._events if record.turn_id == turn_id]

    def last(self, count: int) -> list[TimelineEvent]:
        if count <= 0:
            return []
        return list(self._events)[-count:]

    def clear(self) -> None:
        """'Forget this conversation': wipes the in-RAM timeline."""
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)
