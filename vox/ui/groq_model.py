"""Qt bridge for real, explicitly started Groq push-to-talk sessions."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from vox.agent.auth_storage import StorageError
from vox.agent.groq_tools import PlannedAction
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.voice.audio import AudioError
from vox.voice.service import GroqVoiceService, Outcome


class GroqViewModel(QObject):
    changed = Signal()

    def __init__(self, services: GroqVoiceService | None = None) -> None:
        super().__init__()
        self._services = services or GroqVoiceService()
        self._state = "idle"
        self._title = "Ready"
        self._detail = "Add your Groq API key to start."
        self._status = "Push to talk or enter a request."
        self._transcript = ""
        self._busy = False
        self._recording = False
        self._cancel = threading.Event()
        self._finish = threading.Event()
        self._pending: PlannedAction | None = None
        self._approval_id: str | None = None
        self._results: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._drain)

    @Property(str, constant=True)  # type: ignore[call-arg]
    def previewLabel(self) -> str:
        return "GROQ"

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def title(self) -> str:
        return self._title

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def detail(self) -> str:
        return self._detail

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def eyebrow(self) -> str:
        return {
            "idle": "STANDING BY",
            "recording": "MICROPHONE ON",
            "thinking": "GROQ IN USE",
            "result": "RESULT",
            "error": "NEEDS ATTENTION",
            "approval": "CONFIRM ACTION",
        }[self._state]

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def accent(self) -> str:
        return {
            "idle": "#a5b2c2",
            "recording": "#ff927f",
            "thinking": "#a394ff",
            "result": "#50dfaa",
            "error": "#ff736d",
            "approval": "#ffae36",
        }[self._state]

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def kind(self) -> str:
        return "idle" if self._state == "idle" else "standard"

    @Property(int, notify=changed)  # type: ignore[call-arg, arg-type]
    def notchWidth(self) -> int:
        return 240 if self._state == "idle" else 460

    @Property(int, notify=changed)  # type: ignore[call-arg, arg-type]
    def notchHeight(self) -> int:
        return 42 if self._state == "idle" else 105

    @Property(bool, constant=True)  # type: ignore[call-arg]
    def reduceMotion(self) -> bool:
        return False

    @Property(bool, notify=changed)  # type: ignore[call-arg, arg-type]
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=changed)  # type: ignore[call-arg, arg-type]
    def recording(self) -> bool:
        return self._recording

    @Property(bool, notify=changed)  # type: ignore[call-arg, arg-type]
    def approvalPending(self) -> bool:
        return self._pending is not None

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def approvalText(self) -> str:
        return self._pending.description if self._pending else ""

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def status(self) -> str:
        return self._status

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def transcript(self) -> str:
        return self._transcript

    @Slot(str)
    def saveKey(self, key: str) -> None:
        if self._busy or self._pending:
            return
        try:
            self._services.save_key(key)
            self._status = "Groq key saved using Windows DPAPI."
            self._state, self._title, self._detail = (
                "idle",
                "Ready",
                "Push to talk or type a request.",
            )
        except (StorageError, ValueError):
            self._state, self._title = "error", "Could not save key"
            self._detail = self._status = "Check the key and Windows credential storage."
        self.changed.emit()

    @Slot()
    def removeKey(self) -> None:
        if self._busy or self._pending:
            return
        try:
            self._services.delete_key()
            self._state, self._title = "idle", "Ready"
            self._detail = self._status = "Saved Groq key removed. Revoke it in Groq if needed."
        except StorageError:
            self._state, self._title = "error", "Could not remove key"
            self._detail = self._status = "Could not remove the local key."
        self.changed.emit()

    @Slot(str, bool, bool)
    def submit(self, text: str, dry_run: bool, speak: bool) -> None:
        if self._busy or self._pending:
            return
        self._transcript = ""
        self._start(
            lambda: self._services.submit(text, dry_run, self._cancel.is_set),
            recording=False,
            speak=speak,
        )

    @Slot(bool, bool)
    def record(self, dry_run: bool, speak: bool) -> None:
        if self._busy or self._pending:
            return
        self._transcript = ""
        self._finish.clear()
        self._start(
            lambda: self._services.voice(
                self._finish.is_set,
                self._cancel.is_set,
                dry_run,
                lambda: self._results.put(("processing", None)),
            ),
            recording=True,
            speak=speak,
        )

    @Slot()
    def finishRecording(self) -> None:
        if self._recording:
            self._finish.set()
            self._status = "Finishing recording…"
            self.changed.emit()

    def _start(self, work: Callable[[], Outcome], *, recording: bool, speak: bool) -> None:
        self._cancel.clear()
        self._busy = True
        self._recording = recording
        self._state = "recording" if recording else "thinking"
        self._title = "Listening" if recording else "Contacting Groq"
        self._detail = (
            "Microphone on: click Finish when done."
            if recording
            else "Your request is sent online."
        )
        self._status = self._detail
        self.changed.emit()

        def run() -> None:
            try:
                outcome = work()
                if outcome.result is not None and speak and not self._cancel.is_set():
                    self._results.put(("speaking", None))
                    try:
                        self._services.speak(outcome.result.evidence, self._cancel.is_set)
                    except Exception:  # noqa: BLE001 - preserve completed action evidence if speech fails
                        outcome = Outcome(
                            result=ToolResult(
                                ok=outcome.result.ok,
                                simulated=outcome.result.simulated,
                                evidence=outcome.result.evidence + " Voice reply unavailable.",
                            ),
                            transcript=outcome.transcript,
                        )
                self._results.put(("outcome", outcome))
            except (ProviderError, StorageError, AudioError) as exc:
                self._results.put(("error", str(exc)))
            except Exception:  # noqa: BLE001 - never expose API keys or arbitrary exception text
                self._results.put(("error", "The request failed unexpectedly."))

        threading.Thread(target=run, name="vox-groq-worker", daemon=True).start()
        self._timer.start()

    @Slot()
    def approve(self) -> None:
        if not self._pending or not self._approval_id or self._busy:
            return
        action, approval_id = self._pending, self._approval_id
        self._pending, self._approval_id = None, None
        if not self._services.registry.resolve_approval(approval_id, True):
            self._error("Approval expired or was already resolved.")
            return
        self._start(
            lambda: Outcome(result=self._services.registry.execute(action, approval_id)),
            recording=False,
            speak=False,
        )

    @Slot()
    def deny(self) -> None:
        if self._pending and self._approval_id:
            self._services.registry.resolve_approval(self._approval_id, False)
            self._pending, self._approval_id = None, None
            self._error("Action declined. Nothing was opened.")

    @Slot()
    def cancel(self) -> None:
        self._cancel.set()
        self._finish.set()
        self._services.registry.approvals.deny_all()
        if self._pending:
            self._pending, self._approval_id = None, None
            self._error("Action cancelled. Nothing was opened.")
        elif self._busy:
            self._status = (
                "Stopping… an action or playback already started may not stop immediately."
            )
            self.changed.emit()

    def _error(self, message: str) -> None:
        self._state, self._title = "error", "Could not complete request"
        self._status = self._detail = message
        self.changed.emit()

    @Slot()
    def _drain(self) -> None:
        while True:
            try:
                kind, value = self._results.get_nowait()
            except queue.Empty:
                return
            if kind in ("processing", "speaking"):
                self._recording = False
                self._state, self._title = (
                    "thinking",
                    "Contacting Groq" if kind == "processing" else "Speaking",
                )
                self._detail = self._status = (
                    "Audio and request sent online."
                    if kind == "processing"
                    else "Playing the spoken reply."
                )
                self.changed.emit()
                continue
            self._timer.stop()
            self._busy, self._recording = False, False
            if kind == "error":
                self._error(value)
                continue
            outcome: Outcome = value
            self._transcript = outcome.transcript
            if self._cancel.is_set():
                self._error("Stopped. An action already started may still have completed.")
            elif outcome.pending is not None:
                self._pending = outcome.pending
                self._approval_id = self._services.registry.request_approval(outcome.pending)
                self._state, self._title = "approval", "Confirmation required"
                self._detail = self._status = (
                    "Review the website below. Approval expires after 15 seconds."
                )
                self.changed.emit()
            elif outcome.result is not None:
                self._state = "result" if outcome.result.ok else "error"
                self._title = "Completed" if outcome.result.ok else "Could not complete request"
                self._detail = self._status = outcome.result.evidence
                self.changed.emit()
            else:
                self._error("No action was performed.")

    def shutdown(self) -> None:
        self._cancel.set()
        self._finish.set()
        self._services.registry.approvals.deny_all()
        self._timer.stop()
