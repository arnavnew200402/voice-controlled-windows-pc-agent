"""A deliberately fixed sandbox walkthrough, not a natural-language router.

All results are read back from in-memory state. This module cannot operate on
real apps or files and is not an execution gate for production tools.
"""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vox.approvals import ApprovalStore, Status, Tier, Via
from vox.events import (
    ApprovalRequested,
    ApprovalResolved,
    DemoEvent,
    Intent,
    Reply,
    StateChanged,
    ToolFinished,
    ToolStarted,
)

Scenario = Literal["open", "delete"]


class DeleteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    folder: Literal["virtual Downloads"] = "virtual Downloads"
    files: tuple[str, ...]


class DemoEngine:
    """Synchronous state machine, driven solely by its owning worker thread."""

    def __init__(self, emit: Callable[[DemoEvent], None]) -> None:
        self._emit = emit
        self.approvals = ApprovalStore()
        self.virtual_apps: set[str] = set()
        self.virtual_downloads = ["example-one.txt", "example-two.txt", "example-three.txt"]
        self.phase = "idle"
        self.scenario: Scenario | None = None
        self.approval_id: str | None = None
        self.args: DeleteArgs | None = None

    def start(self, scenario: Scenario) -> bool:
        if self.phase != "idle" or scenario not in ("open", "delete"):
            return False
        self.scenario = scenario
        self.phase = "thinking"
        self._emit(StateChanged(state="thinking", reason="Preparing a simulated action"))
        summary = "Open Notepad in the sandbox" if scenario == "open" else "Clear virtual Downloads"
        self._emit(Intent(summary=summary))
        return True

    def advance(self) -> None:
        if self.phase == "thinking":
            if self.scenario == "delete":
                self.args = DeleteArgs(files=tuple(self.virtual_downloads))
                approval = self.approvals.request("delete_virtual", self.args, Tier.CONFIRM)
                self.approval_id = approval.id
                self.phase = "approval"
                self._emit(StateChanged(state="approval", reason="Simulated confirmation required"))
                self._emit(
                    ApprovalRequested(
                        id=approval.id,
                        title=f"Remove {len(self.args.files)} virtual files?",
                        details="Sandbox only · no real files are touched",
                        expires_at=approval.expires_at,
                    )
                )
            else:
                self.phase = "acting"
                self._emit(StateChanged(state="acting", reason="Running a simulated tool"))
                self._emit(ToolStarted(name="open_virtual_app", title="Opening virtual Notepad"))
        elif self.phase == "approval" and self.approval_id is not None:
            entry = self.approvals.get(self.approval_id)
            if entry is None or entry.status == Status.EXPIRED:
                self._emit(ApprovalResolved(id=self.approval_id, decision="expired", via="timeout"))
                self._reply("The simulated request expired. Nothing was changed.")
        elif self.phase == "acting":
            if self.scenario == "open":
                self.virtual_apps.add("Notepad")
                ok = "Notepad" in self.virtual_apps
                evidence = "Virtual Notepad is open." if ok else "Virtual Notepad did not open."
                self._emit(ToolFinished(name="open_virtual_app", ok=ok, evidence_summary=evidence))
                self._reply(evidence)
            else:
                # Recheck the snapshot before consuming the exact approval.
                if (
                    self.args is None
                    or self.approval_id is None
                    or self.args.files != tuple(self.virtual_downloads)
                    or not self.approvals.consume(
                        self.approval_id, "delete_virtual", self.args, tier=Tier.CONFIRM
                    )
                ):
                    self.approvals.deny_all()
                    self._reply("The simulated action was not approved. Nothing was changed.")
                    return
                self.virtual_downloads.clear()
                ok = not self.virtual_downloads
                evidence = (
                    "Virtual Downloads is empty." if ok else "Virtual Downloads is not empty."
                )
                self._emit(ToolFinished(name="delete_virtual", ok=ok, evidence_summary=evidence))
                self._reply(evidence)
        elif self.phase == "speaking":
            self.phase = "idle"
            self.scenario = None
            self._emit(StateChanged(state="idle", reason="Simulation complete"))

    def resolve(self, approve: bool) -> bool:
        if self.phase != "approval" or self.approval_id is None:
            return False
        approval_id = self.approval_id
        if not self.approvals.resolve(approval_id, approve=approve, via=Via.CLICK):
            return False
        self._emit(
            ApprovalResolved(
                id=approval_id, decision="approved" if approve else "denied", via="demo click"
            )
        )
        if approve:
            self.phase = "acting"
            self._emit(StateChanged(state="acting", reason="Running a simulated tool"))
            self._emit(ToolStarted(name="delete_virtual", title="Removing virtual files"))
        else:
            self._reply("Simulated request denied. Nothing was changed.")
        return True

    def stop(self) -> None:
        approval_id = self.approval_id if self.phase == "approval" else None
        self.approvals.deny_all()
        if approval_id:
            self._emit(ApprovalResolved(id=approval_id, decision="denied", via="stop"))
        self.phase = "idle"
        self.scenario = None
        self.approval_id = None
        self.args = None
        self._emit(Reply(text="Simulation stopped. No real PC actions were performed."))
        self._emit(StateChanged(state="idle", reason="Stopped"))

    def _reply(self, text: str) -> None:
        self.phase = "speaking"
        self.approval_id = None
        self.args = None
        self._emit(StateChanged(state="speaking", reason="Simulation result"))
        self._emit(Reply(text=text))
