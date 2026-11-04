"""Preview UI bridge for the limited real online text path.

Worker threads never touch Qt. This is not the final voice agent or an approval UI.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Literal

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from vox.agent.auth_storage import StorageError, windows_store
from vox.agent.chatgpt import ChatGPTProvider
from vox.agent.chatgpt_auth import AuthError, sign_in
from vox.agent.tools import DryRunBackend, ToolRegistry, ToolResult
from vox.agent.turn import run_turn
from vox.agent.windows import WindowsNotepadBackend


class LiveServices:
    def login(self, cancelled: Callable[[], bool]) -> ToolResult:
        try:
            sign_in(windows_store(), cancelled=cancelled)
            return ToolResult(ok=True, evidence="Signed in to ChatGPT.")
        except (StorageError, AuthError):
            return ToolResult(
                ok=False,
                evidence="Sign-in failed or was cancelled. Check Windows and your ChatGPT plan.",
            )

    def text(self, text: str, dry_run: bool, cancelled: Callable[[], bool]) -> ToolResult:
        try:
            _, session = windows_store().load()
            if session is None:
                return ToolResult(ok=False, evidence="Sign in to ChatGPT first.")
            if session.expires_at <= time.time() + 30:
                return ToolResult(ok=False, evidence="Session expired. Sign in again.")
            provider = ChatGPTProvider(session)
            backend = DryRunBackend() if dry_run else WindowsNotepadBackend()
            return run_turn(text, provider, ToolRegistry(backend), cancelled=cancelled)
        except (StorageError, ValueError):
            return ToolResult(
                ok=False, evidence="Could not load ChatGPT sign-in on this Windows account."
            )


class LiveViewModel(QObject):
    changed = Signal()
    reduceMotionChanged = Signal()

    def __init__(self, services: LiveServices | None = None) -> None:
        super().__init__()
        self._services = services or LiveServices()
        self._state = "idle"
        self._title = "Ready for a text request"
        self._detail = "Sign in to ChatGPT to get started."
        self._status = "Only Notepad is supported. Dry run is on by default."
        self._busy = False
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._results: queue.Queue[ToolResult] = queue.Queue()
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._drain)

    @Property(str, constant=True)  # type: ignore[call-arg]
    def previewLabel(self) -> str:
        return "ONLINE"

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
            "thinking": "CHATGPT IN USE",
            "result": "RESULT",
            "error": "NEEDS ATTENTION",
        }[self._state]

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def accent(self) -> str:
        return {"idle": "#a5b2c2", "thinking": "#a394ff", "result": "#50dfaa", "error": "#ff736d"}[
            self._state
        ]

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

    @Property(str, notify=changed)  # type: ignore[call-arg, arg-type]
    def status(self) -> str:
        return self._status

    @Slot()
    def login(self) -> None:
        self._start("login", "", True)

    @Slot(str, bool)
    def submit(self, text: str, dry_run: bool) -> None:
        if not text.strip() or len(text) > 4000:
            self._state = "error"
            self._title = "Request is empty or too long"
            self._detail = "Enter up to 4,000 characters."
            self._status = self._detail
            self.changed.emit()
            return
        self._start("text", text, dry_run)

    def _start(self, operation: Literal["login", "text"], text: str, dry_run: bool) -> None:
        if self._busy:
            return
        self._cancel.clear()
        self._busy = True
        self._state = "thinking"
        self._title = "Connecting to ChatGPT"
        self._detail = (
            "A browser sign-in is opening."
            if operation == "login"
            else "Your request is sent online."
        )
        self._status = self._detail
        self.changed.emit()

        def run() -> None:
            try:
                result = (
                    self._services.login(self._cancel.is_set)
                    if operation == "login"
                    else self._services.text(text, dry_run, self._cancel.is_set)
                )
            except Exception:  # noqa: BLE001 - do not leak credentials from unexpected errors
                result = ToolResult(ok=False, evidence="The request failed unexpectedly.")
            self._results.put(result)

        self._worker = threading.Thread(target=run, name="vox-online-preview", daemon=True)
        self._worker.start()
        self._timer.start()

    @Slot()
    def cancel(self) -> None:
        if self._busy:
            self._cancel.set()
            self._status = "Stopping… an action already started cannot be undone."
            self.changed.emit()

    @Slot()
    def _drain(self) -> None:
        try:
            result = self._results.get_nowait()
        except queue.Empty:
            return
        self._timer.stop()
        self._busy = False
        self._state = "result" if result.ok else "error"
        self._title = "Completed" if result.ok else "Could not complete request"
        self._detail = result.evidence
        self._status = result.evidence
        self.changed.emit()

    def shutdown(self) -> None:
        self._cancel.set()
        self._timer.stop()
        # Calls may be inside a bounded network timeout. Never block the UI on shutdown.
