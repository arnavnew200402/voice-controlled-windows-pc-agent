"""Actions ledger: what Vox verifiably did (spec 4.3).

Written deterministically from tool results — never by an LLM — so "undo
that", "what did you just do?" and contradiction checks ("open the file I
just deleted") all read from one source of truth shared with the prompt.
Undo itself stays an ordinary tiered tool call (L-09).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from vox.engine.clock import Clock, SystemClock

TargetState = Literal["deleted", "acted_on", "unknown"]


@dataclass
class ActionRecord:
    action_id: str
    turn_id: str
    tool: str
    args_redacted: dict[str, Any] = field(default_factory=dict)
    ok: bool = False
    evidence: str = ""
    target_label: str = ""
    undo_info: dict[str, Any] | None = None
    t_wall: float = 0.0
    undone: bool = False


class ActionsLedger:
    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._records: list[ActionRecord] = []
        self._sequence = 0

    def record(
        self,
        *,
        turn_id: str,
        tool: str,
        ok: bool,
        evidence: str,
        args_redacted: dict[str, Any] | None = None,
        target_label: str = "",
        undo_info: dict[str, Any] | None = None,
    ) -> ActionRecord:
        self._sequence += 1
        record = ActionRecord(
            action_id=f"act-{self._sequence}",
            turn_id=turn_id,
            tool=tool,
            args_redacted=dict(args_redacted or {}),
            ok=ok,
            evidence=evidence,
            target_label=target_label,
            undo_info=undo_info,
            t_wall=self._clock.wall(),
        )
        self._records.append(record)
        return record

    def restore(self, records: list[ActionRecord]) -> None:
        """Replace contents from a checkpoint (crash restore)."""
        self._records = list(records)
        self._sequence = len(self._records)

    def records(self) -> list[ActionRecord]:
        return list(self._records)

    def last(self, count: int = 10) -> list[ActionRecord]:
        return self._records[-count:] if count > 0 else []

    def last_undoable(self) -> ActionRecord | None:
        for record in reversed(self._records):
            if record.ok and record.undo_info is not None and not record.undone:
                return record
        return None

    def mark_undone(self, action_id: str) -> bool:
        for record in self._records:
            if record.action_id == action_id:
                record.undone = True
                return True
        return False

    def target_state(self, label_fragment: str) -> TargetState:
        """Most recent known fate of a target (edge case 12)."""
        needle = label_fragment.strip().lower()
        if not needle:
            return "unknown"
        for record in reversed(self._records):
            if needle in record.target_label.lower() and record.ok:
                return "deleted" if record.tool == "delete_file" else "acted_on"
        return "unknown"

    def render(self, limit: int = 10) -> str:
        lines = []
        for record in self.last(limit):
            status = "ok" if record.ok else "failed"
            target = f" [{record.target_label}]" if record.target_label else ""
            lines.append(f"{record.action_id} {record.tool} {status}{target}: {record.evidence}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._records.clear()
