"""Qt bridge for the Groq voice UI: typed requests plus hands-free wake word."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from vox.agent.auth_storage import StorageError
from vox.agent.groq_tools import (
    PlannedAction,
    ScrollRequest,
    TypingRequest,
    WindowActionRequest,
)
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.agent.windows_control import WindowRef
from vox.voice.audio import AudioError, iter_microphone_frames, record_until_silence
from vox.voice.handsfree import CaptureCommand, FrameSource, HandsFreeController
from vox.voice.service import GroqVoiceService, Outcome
from vox.voice.wake import VoskWakeEngine, WakeEngine


class GroqViewModel(QObject):
    changed = Signal()

    def __init__(self, services: GroqVoiceService | None = None) -> None:
        super().__init__()
        self._services = services or GroqVoiceService()
        self._state = "idle"
        self._title = "Ready"
        self._detail = "Add your Groq API key to start."
        self._status = "Turn on Hands-free or enter a request."
        self._transcript = ""
        self._busy = False
        self._recording = False
        self._hands_free = False
        self._controller: HandsFreeController | None = None
        # Injection seams for tests; None means use the real audio/wake stack.
        self._hf_engine_factory: Callable[[], WakeEngine] | None = None
        self._hf_frame_source: FrameSource | None = None
        self._hf_capture_command: CaptureCommand | None = None
        self._cancel = threading.Event()
        self._pending: PlannedAction | None = None
        self._approval_id: str | None = None
        self._windows: list[WindowRef] = []
        self._selected_window = -1
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
            "wake": "SAY “HI VOX”",
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
            "wake": "#50dfaa",
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
    def handsFree(self) -> bool:
        return self._hands_free

    @Property(bool, notify=changed)  # type: ignore[call-arg, arg-type]
    def approvalPending(self) -> bool:
        return self._pending is not None

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def approvalText(self) -> str:
        return self._pending.description if self._pending else ""

    @Property(bool, notify=changed)  # type: ignore[call-arg, arg-type]
    def needsWindow(self) -> bool:
        if not self._pending:
            return False
        return isinstance(self._pending.args, (TypingRequest, ScrollRequest, WindowActionRequest))

    @Property("QStringList", notify=changed)  # type: ignore[call-arg, arg-type]
    def windowChoices(self) -> list[str]:
        return [
            f"Window: {window.title} · PID {window.pid} · {window.window_class}"
            for window in self._windows
        ]

    @Slot(int)
    def selectWindow(self, index: int) -> None:
        self._selected_window = index if 0 <= index < len(self._windows) else -1

    @Slot()
    def refreshWindows(self) -> None:
        if not self.needsWindow:
            return
        try:
            self._windows = self._services.registry.list_windows()
        except Exception:  # noqa: BLE001 - window enumeration must fail closed
            self._windows = []
        self._selected_window = -1
        self.changed.emit()

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
                "Turn on Hands-free and say “Hi Vox”, or type a request.",
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
        if self._busy or self._pending or self._hands_free:
            return
        self._transcript = ""
        self._start(
            lambda: self._services.submit(text, dry_run, self._cancel.is_set),
            recording=False,
            speak=speak,
        )

    @Slot(bool, bool, bool)
    def setHandsFree(self, enabled: bool, dry_run: bool, speak: bool) -> None:
        if enabled == self._hands_free:
            return
        if enabled:
            if self._busy or self._pending:
                return
            self._cancel.clear()
            self._transcript = ""
            controller = HandsFreeController(
                engine_factory=self._hf_engine_factory or VoskWakeEngine,
                frame_source=self._hf_frame_source or iter_microphone_frames,
                capture_command=self._hf_capture_command or record_until_silence,
                process_audio=self._services.process_audio,
                speak_result=self._services.speak,
                on_state=lambda state: self._results.put(("hf_state", state)),
                on_outcome=lambda outcome: self._results.put(("hf_outcome", outcome)),
                on_error=lambda message: self._results.put(("hf_error", message)),
            )
            self._controller = controller
            self._hands_free = True
            self._timer.start()
            controller.start(dry_run=dry_run, speak=speak)
        else:
            self._hands_free = False
            if self._controller is not None:
                self._controller.stop()
            self._recording = False
            if not self._pending:
                self._state, self._title = "idle", "Ready"
                self._detail = self._status = "Hands-free is off. The microphone is closed."
        self.changed.emit()

    def _start(self, work: Callable[[], Outcome], *, recording: bool, speak: bool) -> None:
        self._cancel.clear()
        self._busy = True
        self._recording = recording
        self._state = "recording" if recording else "thinking"
        self._title = "Listening" if recording else "Contacting Groq"
        self._detail = (
            "Microphone on: speak your request." if recording else "Your request is sent online."
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
        if not self._pending or self._busy:
            return
        action, approval_id = self._pending, self._approval_id
        if self.needsWindow:
            if not 0 <= self._selected_window < len(self._windows):
                self._status = "Select a target window before confirming."
                self.changed.emit()
                return
            window = self._windows[self._selected_window]
            try:
                if isinstance(action.args, TypingRequest):
                    action = self._services.registry.bind_typing(action, window)
                elif isinstance(action.args, ScrollRequest):
                    action = self._services.registry.bind_scroll(action, window)
                elif isinstance(action.args, WindowActionRequest):
                    action = self._services.registry.bind_window_action(action, window)
                else:
                    self._error("Unsupported window action; nothing was performed.")
                    return
                approval_id = self._services.registry.request_approval(action)
            except (ValueError, RuntimeError):
                self._error("Could not bind the selected window; no action was performed.")
                return
        if not approval_id:
            self._error("Approval is unavailable. No action was performed.")
            return
        self._pending, self._approval_id = None, None
        self._windows = []
        self._selected_window = -1
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
        if self._pending:
            if self._approval_id:
                self._services.registry.resolve_approval(self._approval_id, False)
            self._pending, self._approval_id = None, None
            self._windows = []
            self._selected_window = -1
            self._error("Action declined. Nothing was performed.")
            if self._controller is not None:
                self._controller.resume()

    @Slot()
    def cancel(self) -> None:
        self._cancel.set()
        if self._controller is not None:
            self._controller.stop()
        self._hands_free = False
        self._recording = False
        self._services.registry.approvals.deny_all()
        if self._pending:
            self._pending, self._approval_id = None, None
            self._windows = []
            self._selected_window = -1
            self._error("Action cancelled. Nothing was performed.")
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
            if kind == "hf_state":
                self._apply_hf_state(value)
                continue
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
            if not self._hands_free:
                self._timer.stop()
            self._busy, self._recording = False, False
            if kind in ("error", "hf_error"):
                self._error(value)
                continue
            outcome: Outcome = value
            self._transcript = outcome.transcript
            if self._cancel.is_set():
                self._error("Stopped. An action already started may still have completed.")
            elif outcome.pending is not None:
                self._pending = outcome.pending
                self._state, self._title = "approval", "Confirmation required"
                if self.needsWindow:
                    self._approval_id = None
                    self.refreshWindows()
                    if isinstance(outcome.pending.args, TypingRequest):
                        self._detail = self._status = (
                            "Choose the exact window and review the text. Position its text cursor first."
                        )
                    elif isinstance(outcome.pending.args, ScrollRequest):
                        self._detail = self._status = (
                            "Select the window where you want to scroll, then confirm."
                        )
                    else:
                        self._detail = self._status = (
                            "Select the window you want to control, then confirm."
                        )
                else:
                    try:
                        self._approval_id = self._services.registry.request_approval(
                            outcome.pending
                        )
                    except (ValueError, RuntimeError):
                        self._pending = None
                        self._error("Could not prepare approval; no action was performed.")
                        continue
                    self._detail = self._status = (
                        "Review the action below. Approval expires after 15 seconds."
                    )
                self.changed.emit()
            elif outcome.result is not None:
                self._state = "result" if outcome.result.ok else "error"
                self._title = "Completed" if outcome.result.ok else "Could not complete request"
                self._detail = self._status = outcome.result.evidence
                self.changed.emit()
                if self._controller is not None:
                    # An approved action finished (or a turn completed): let
                    # the wake-word loop listen again.
                    self._controller.resume()
            else:
                self._error("No action was performed.")

    def _apply_hf_state(self, state: str) -> None:
        if state == "starting":
            self._state, self._title = "thinking", "Starting hands-free"
            self._detail = (
                "Preparing the on-device wake word. First use downloads a small offline model."
            )
        elif state == "wake":
            self._recording = False
            self._state, self._title = "wake", "Hands-free on"
            self._detail = "Say “Hi Vox”, then your request. Wake listening stays on this PC."
        elif state == "command":
            self._recording = True
            self._state, self._title = "recording", "Listening"
            self._detail = "Speak your request — Vox stops recording when you finish."
        elif state == "processing":
            self._recording = False
            self._state, self._title = "thinking", "Contacting Groq"
            self._detail = "Audio and request sent online."
        elif state == "speaking":
            self._state, self._title = "thinking", "Speaking"
            self._detail = "Playing the spoken reply."
        elif state == "off":
            self._recording = False
            was_on = self._hands_free
            self._hands_free = False
            self._controller = None
            if self._state != "error" and not self._pending:
                self._state, self._title = "idle", "Ready"
                self._detail = "Turn on Hands-free or type a request."
                if was_on:
                    self._status = self._detail
            if not self._busy:
                self._timer.stop()
            self.changed.emit()
            return
        else:
            return
        self._status = self._detail
        self.changed.emit()

    def shutdown(self) -> None:
        self._cancel.set()
        if self._controller is not None:
            self._controller.stop()
        self._services.registry.approvals.deny_all()
        self._timer.stop()
