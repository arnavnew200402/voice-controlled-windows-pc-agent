"""Typed events for the native sandbox demo, not yet a production event ledger."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1] = 1


class StateChanged(Event):
    type: Literal["state"] = "state"
    state: Literal["idle", "thinking", "acting", "approval", "speaking", "error"]
    reason: str


class Intent(Event):
    type: Literal["intent"] = "intent"
    summary: str


class ToolStarted(Event):
    type: Literal["tool_started"] = "tool_started"
    name: str
    title: str


class ToolFinished(Event):
    type: Literal["tool_finished"] = "tool_finished"
    name: str
    ok: bool
    evidence_summary: str


class ApprovalRequested(Event):
    type: Literal["approval_requested"] = "approval_requested"
    id: str
    title: str
    details: str
    expires_at: float


class ApprovalResolved(Event):
    type: Literal["approval_resolved"] = "approval_resolved"
    id: str
    decision: Literal["approved", "denied", "expired"]
    via: str


class Reply(Event):
    type: Literal["reply"] = "reply"
    text: str
    spoken: bool = False


DemoEvent = (
    StateChanged
    | Intent
    | ToolStarted
    | ToolFinished
    | ApprovalRequested
    | ApprovalResolved
    | Reply
)


class Endpointing(Event):
    type: Literal["endpointing"] = "endpointing"
    level: Literal["soft", "hard"]
    turn_id: str


class TurnOpened(Event):
    type: Literal["turn_opened"] = "turn_opened"
    turn_id: str
    trigger: Literal["hotkey", "wake", "followup", "typed", "test"]


class TurnClosed(Event):
    type: Literal["turn_closed"] = "turn_closed"
    turn_id: str
    outcome: Literal["completed", "no_speech", "error", "silent"]


class TurnCancelled(Event):
    type: Literal["turn_cancelled"] = "turn_cancelled"
    turn_id: str
    reason: str


class Contextualized(Event):
    type: Literal["contextualized"] = "contextualized"
    turn_id: str
    standalone: str
    refs: tuple[str, ...] = ()


class AckPlayed(Event):
    type: Literal["ack_played"] = "ack_played"
    kind: str


class ClarificationRequested(Event):
    type: Literal["clarification_requested"] = "clarification_requested"
    turn_id: str
    question: str


class ClarificationResolved(Event):
    type: Literal["clarification_resolved"] = "clarification_resolved"
    turn_id: str
    answer: str


class DictationState(Event):
    type: Literal["dictation_state"] = "dictation_state"
    active: bool


class MemoryUpdated(Event):
    type: Literal["memory_updated"] = "memory_updated"
    layer: str


class LatencySample(Event):
    type: Literal["latency_sample"] = "latency_sample"
    turn_id: str
    stage: str
    ms: float


class WakeDetected(Event):
    type: Literal["wake_detected"] = "wake_detected"
    stage1_score: float
    phrase: str


class WakeVerified(Event):
    type: Literal["wake_verified"] = "wake_verified"
    ok: bool
    reason: str
    ms: float


class WakeTimeout(Event):
    type: Literal["wake_timeout"] = "wake_timeout"


class TriggerSource(Event):
    type: Literal["trigger_source"] = "trigger_source"
    turn_id: str
    source: Literal["hotkey", "wake", "followup", "typed"]


LiveEvent = (
    Endpointing
    | TurnOpened
    | TurnClosed
    | TurnCancelled
    | Contextualized
    | AckPlayed
    | ClarificationRequested
    | ClarificationResolved
    | DictationState
    | MemoryUpdated
    | LatencySample
    | WakeDetected
    | WakeVerified
    | WakeTimeout
    | TriggerSource
    | ToolStarted
    | ToolFinished
    | ApprovalRequested
    | ApprovalResolved
)
