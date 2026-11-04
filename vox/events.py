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
