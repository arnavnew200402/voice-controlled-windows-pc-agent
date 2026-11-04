"""Presentation-only state for the synthetic notch preview."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from vox.demo.worker import DemoWorker
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


@dataclass(frozen=True)
class PreviewState:
    title: str
    eyebrow: str
    detail: str
    accent: str
    width: int
    height: int
    kind: str


STATES: dict[str, PreviewState] = {
    "idle": PreviewState("Ready when you are", "STANDING BY", "", "#a5b2c2", 240, 42, "idle"),
    "wake": PreviewState(
        "I'm listening",
        "WAKE DETECTED",
        "Go ahead, tell me what you need.",
        "#8ab4ff",
        360,
        78,
        "standard",
    ),
    "listening": PreviewState(
        "Listening",
        "VOICE INPUT",
        "Open Chrome and search for local models…",
        "#4da3ff",
        440,
        138,
        "wave",
    ),
    "thinking": PreviewState(
        "Working it out", "THINKING", "Finding the best next step", "#a394ff", 420, 104, "thinking"
    ),
    "acting": PreviewState(
        "Opening Chrome",
        "IN PROGRESS  ·  STEP 1 OF 2",
        "Searching for local models next",
        "#50dfaa",
        460,
        118,
        "action",
    ),
    "approval": PreviewState(
        "Move 14 files to Recycle Bin?",
        "APPROVAL NEEDED",
        "Downloads  ·  This action can be undone",
        "#ffae36",
        490,
        188,
        "approval",
    ),
    "speaking": PreviewState(
        "Here's what I found.",
        "REPLY",
        "I opened Chrome and searched for local models.",
        "#79eddc",
        460,
        140,
        "reply",
    ),
    "error": PreviewState(
        "Couldn't open Chrome",
        "NEEDS ATTENTION",
        "Try again or check that the app is installed.",
        "#ff736d",
        440,
        108,
        "standard",
    ),
    "echo": PreviewState("Volume", "QUICK ACTION", "30%", "#79eddc", 320, 78, "echo"),
    "panel": PreviewState(
        "Your space",
        "QUICK CONTROLS",
        "A little more room to see what's happening.",
        "#a394ff",
        520,
        232,
        "panel",
    ),
}


class NotchDemoModel(QObject):
    changed = Signal()
    reduceMotionChanged = Signal()
    demoChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"
        self._reduce_motion = False
        self._worker: DemoWorker | None = None
        self._busy = False
        self._stopping = False
        self._approval_pending = False
        self._live_title = ""
        self._live_detail = ""
        self._demo_status = "Choose a simulation to see the connected event flow."
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._drain_events)

    @Property(str, constant=True)  # type: ignore[call-arg]
    def previewLabel(self) -> str:
        return "DEMO"

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def title(self) -> str:
        return self._live_title or STATES[self._state].title

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def eyebrow(self) -> str:
        return STATES[self._state].eyebrow

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def detail(self) -> str:
        return self._live_detail or STATES[self._state].detail

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def accent(self) -> str:
        return STATES[self._state].accent

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def kind(self) -> str:
        return STATES[self._state].kind

    @Property(int, notify=changed)  # type: ignore[call-arg, arg-type]
    def notchWidth(self) -> int:
        return STATES[self._state].width

    @Property(int, notify=changed)  # type: ignore[call-arg, arg-type]
    def notchHeight(self) -> int:
        return STATES[self._state].height

    @Property(bool, notify=reduceMotionChanged)  # type: ignore[call-arg, arg-type]
    def reduceMotion(self) -> bool:
        return self._reduce_motion

    @Property(bool, notify=demoChanged)  # type: ignore[call-arg, arg-type]
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=demoChanged)  # type: ignore[call-arg, arg-type]
    def stopping(self) -> bool:
        return self._stopping

    @Property(bool, notify=demoChanged)  # type: ignore[call-arg, arg-type]
    def approvalPending(self) -> bool:
        return self._approval_pending

    @Property(str, notify=demoChanged)  # type: ignore[call-arg, arg-type]
    def demoStatus(self) -> str:
        return self._demo_status

    @Slot(str)
    def startDemo(self, scenario: str) -> None:
        if self._busy or scenario not in ("open", "delete"):
            return
        if self._worker is not None and not self._worker.alive():
            self._worker.close()
            self._worker = None
        if self._worker is None:
            self._worker = DemoWorker()
        self._busy = True
        self._stopping = False
        self._approval_pending = False
        self._live_title = ""
        self._live_detail = ""
        self._demo_status = "Starting sandbox simulation…"
        self.demoChanged.emit()
        self._timer.start()
        if scenario == "open":
            self._worker.start("open")
        else:
            self._worker.start("delete")

    @Slot(bool)
    def resolveDemo(self, approve: bool) -> None:
        if self._worker is not None and self._busy and self._approval_pending:
            self._approval_pending = False
            self.demoChanged.emit()
            self._worker.resolve(approve)

    @Slot()
    def stopDemo(self) -> None:
        if self._worker is not None and self._busy and not self._stopping:
            self._stopping = True
            self._approval_pending = False
            self._demo_status = "Stopping simulation…"
            self.demoChanged.emit()
            self._worker.stop()

    def shutdown(self) -> None:
        self._timer.stop()
        if self._worker is not None:
            self._worker.close()
            self._worker = None

    @Slot()
    def _drain_events(self) -> None:
        if self._worker is None:
            return
        while True:
            try:
                event = self._worker.events.get_nowait()
            except Empty:
                break
            self._apply_event(event)

    def _apply_event(self, event: DemoEvent) -> None:
        if isinstance(event, StateChanged):
            self._state = event.state
            self._live_title = ""
            self._live_detail = ""
            if event.state == "idle":
                self._busy = False
                self._stopping = False
                self._approval_pending = False
                self._timer.stop()
            if event.state != "idle":
                self._demo_status = event.reason
            self.changed.emit()
        elif isinstance(event, Intent):
            self._live_detail = event.summary
            self._demo_status = event.summary
            self.changed.emit()
        elif isinstance(event, ToolStarted):
            self._live_title = event.title
            self._live_detail = "Running in the sandbox only"
            self._demo_status = event.title
            self.changed.emit()
        elif isinstance(event, ToolFinished):
            self._demo_status = event.evidence_summary
        elif isinstance(event, ApprovalRequested):
            self._live_title = event.title
            self._live_detail = event.details
            self._approval_pending = not self._stopping
            if not self._stopping:
                self._demo_status = "Confirm or deny in the studio · expires after 15 seconds"
            self.changed.emit()
        elif isinstance(event, ApprovalResolved):
            self._approval_pending = False
            self._demo_status = "Simulation " + event.decision
        elif isinstance(event, Reply):
            self._live_title = "Simulation result"
            self._live_detail = event.text
            self._demo_status = event.text
            self.changed.emit()
        self.demoChanged.emit()

    @Slot(str)
    def selectState(self, name: str) -> None:
        if not self._busy and name in STATES:
            self._state = name
            self._live_title = ""
            self._live_detail = ""
            self.changed.emit()

    @Slot()
    def nextState(self) -> None:
        states = tuple(STATES)
        self.selectState(states[(states.index(self._state) + 1) % len(states)])

    @Slot(bool)
    def setReduceMotion(self, value: bool) -> None:
        if value != self._reduce_motion:
            self._reduce_motion = value
            self.reduceMotionChanged.emit()
