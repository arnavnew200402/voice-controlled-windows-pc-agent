"""Qt smoke tests: synthetic preview only; no desktop or audio actions."""

import os

import pytest

try:
    from PySide6.QtCore import QEventLoop, QMetaObject, QObject, Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickWindow

    from vox.ui.app import close_preview, create_preview
    from vox.ui.model import STATES
except ImportError as exc:
    if os.environ.get("VOX_REQUIRE_UI_TESTS") == "1":
        raise
    pytest.skip(f"Qt UI runtime unavailable: {exc}", allow_module_level=True)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_preview_loads_and_renders_every_state():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine, model = create_preview(app)
    warnings = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry) for entry in entries))
    root = engine.rootObjects()[0]
    notch = root.findChild(QQuickWindow, "notchWindow")
    assert notch is not None
    assert notch.flags() & Qt.WindowType.WindowTransparentForInput
    assert notch.flags() & Qt.WindowType.WindowDoesNotAcceptFocus
    wait(100)
    assert notch.isVisible()
    for name, preview in STATES.items():
        model.selectState(name)
        assert model.state == name
        assert model.notchWidth == preview.width
        assert model.notchHeight == preview.height
        wait(60)
        assert not notch.grabWindow().isNull(), name
    model.selectState("not-a-state")
    assert model.state == "panel"
    model.setReduceMotion(True)
    assert model.reduceMotion
    model.nextState()
    assert model.state == "idle"
    assert not warnings
    close_preview(engine)


def wait_until(predicate, timeout_ms=5000):
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while not predicate() and time.monotonic() < deadline:
        wait(25)
    assert predicate(), "timed out waiting for preview state"


def test_studio_buttons_drive_sandbox_events():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine, model = create_preview(app)
    root = engine.rootObjects()[0]
    delete_button = root.findChild(QObject, "demoDelete")
    approve_button = root.findChild(QObject, "demoApprove")
    open_button = root.findChild(QObject, "demoOpen")
    stop_button = root.findChild(QObject, "demoStop")
    assert all(
        button is not None for button in (delete_button, approve_button, open_button, stop_button)
    )
    assert QMetaObject.invokeMethod(delete_button, "clicked")
    wait_until(lambda: model.approvalPending)
    assert model.state == "approval"
    assert "virtual" in model.title.lower()
    assert QMetaObject.invokeMethod(approve_button, "clicked")
    wait_until(lambda: not model.busy)
    assert "Virtual Downloads is empty" in model.demoStatus
    assert QMetaObject.invokeMethod(open_button, "clicked")
    wait_until(lambda: model.busy)
    assert QMetaObject.invokeMethod(stop_button, "clicked")
    model.stopDemo()  # A second stop while one is pending is harmless.
    wait_until(lambda: not model.busy)
    assert "stopped" in model.demoStatus.lower()
    assert QMetaObject.invokeMethod(open_button, "clicked")
    wait_until(lambda: not model.busy)
    assert "Virtual Notepad is open" in model.demoStatus
    model.startDemo("delete")
    worker = model._worker
    assert worker is not None
    close_preview(engine)
    assert not worker.alive()


def test_groq_ui_is_wired_to_background_services():
    import threading

    from vox.agent.groq_tools import GroqRegistry
    from vox.agent.tools import ToolResult
    from vox.ui.app import create_live
    from vox.voice.service import Outcome

    class Backend:
        def open_app(self, name):
            raise AssertionError("real app must not open")

        def open_website(self, url):
            raise AssertionError("real browser must not open")

    class Services:
        def __init__(self):
            self.thread_id = 0
            self.last_request = None
            self.saved = None
            self.registry = GroqRegistry(Backend())

        def save_key(self, key):
            self.saved = key

        def engine_mode(self):
            return "legacy"

        def submit(self, text, dry_run, cancelled):
            self.thread_id = threading.get_ident()
            self.last_request = (text, dry_run)
            return Outcome(result=ToolResult(ok=True, evidence="Fake result."))

        def speak(self, text, cancelled):
            pass

    app = QGuiApplication.instance() or QGuiApplication([])
    engine, model = create_live(app)
    services = Services()
    model._services = services
    root = engine.rootObjects()[0]
    key_input = root.findChild(QObject, "keyInput")
    save = root.findChild(QObject, "saveKeyButton")
    input_field = root.findChild(QObject, "requestInput")
    dry_run = root.findChild(QObject, "dryRun")
    speak = root.findChild(QObject, "speak")
    run = root.findChild(QObject, "runButton")
    assert all(x is not None for x in (key_input, save, input_field, dry_run, speak, run))
    key_input.setProperty("text", "fake-key")
    assert QMetaObject.invokeMethod(save, "clicked")
    assert services.saved == "fake-key"
    assert key_input.property("text") == ""
    assert dry_run.property("checked") is False
    dry_run.setProperty("checked", True)
    speak.setProperty("checked", False)
    input_field.setProperty("text", "Open Notepad")
    assert QMetaObject.invokeMethod(run, "clicked")
    wait_until(lambda: not model.busy)
    assert services.last_request == ("Open Notepad", True)
    assert services.thread_id != threading.get_ident()
    assert model.status == "Fake result."
    close_preview(engine)


def handsfree_harness(model, services):
    """Inject a fake wake engine, frame source and command capture."""
    import threading
    import time

    wake_gate = threading.Event()

    class WakeEngine:
        def __init__(self):
            self.on_heard = None

        def set_on_heard(self, callback):
            self.on_heard = callback

        def feed(self, frame):
            if wake_gate.is_set():
                if self.on_heard is not None:
                    self.on_heard("hi box")
                return True
            return False

    def frame_source(cancelled):
        while not cancelled():
            yield b"frame"
            time.sleep(0.01)

    model._hf_engine_factory = lambda: WakeEngine()
    model._hf_frame_source = frame_source
    model._hf_capture_command = lambda cancelled: b"fake command"
    model._services = services
    return wake_gate


def test_window_selection_and_typing_confirmation_are_wired():
    from vox.agent.groq_tools import GroqRegistry
    from vox.agent.tools import ToolResult
    from vox.agent.windows_control import WindowRef
    from vox.ui.app import create_live
    from vox.voice.service import Outcome

    class Backend:
        def __init__(self):
            self.calls = []

        def open_app(self, name):
            raise AssertionError("not expected")

        def open_website(self, url):
            raise AssertionError("not expected")

        def open_folder(self, path):
            raise AssertionError("not expected")

        def resolve_folder(self, target):
            raise AssertionError("not expected")

        def list_windows(self):
            return [
                WindowRef(
                    hwnd=10,
                    pid=100,
                    created=1,
                    focus_hwnd=20,
                    title="Notepad",
                    window_class="Notepad",
                )
            ]

        def type_text(self, target, text):
            self.calls.append((target.title, text))
            return ToolResult(ok=True, evidence="Fake typing action completed.")

    class Services:
        def __init__(self):
            self.backend = Backend()
            self.registry = GroqRegistry(self.backend)

        def engine_mode(self):
            return "legacy"

        def process_audio(self, wav, dry_run, cancelled):
            assert wav == b"fake command"
            action = self.registry.plan(
                {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "type_text",
                                "arguments": '{"text":"hello","target_hint":"Notepad"}',
                            },
                        }
                    ]
                }
            )
            return Outcome(pending=action, transcript="type hello in notepad")

        def speak(self, text, cancelled):
            pass

    app = QGuiApplication.instance() or QGuiApplication([])
    engine, model = create_live(app)
    services = Services()
    wake_gate = handsfree_harness(model, services)
    root = engine.rootObjects()[0]
    speak = root.findChild(QObject, "speak")
    speak.setProperty("checked", False)
    toggle = root.findChild(QObject, "handsFreeToggle")
    approve = root.findChild(QObject, "approveButton")
    assert toggle is not None and approve is not None
    assert QMetaObject.invokeMethod(toggle, "toggle")
    wait_until(lambda: model.handsFree and model.state == "wake")
    wake_gate.set()
    wait_until(lambda: model.approvalPending and model.needsWindow)
    wake_gate.clear()
    assert len(model.windowChoices) == 1 and "Notepad" in model.windowChoices[0]
    model.selectWindow(0)
    assert QMetaObject.invokeMethod(approve, "clicked")
    wait_until(lambda: services.backend.calls == [("Notepad", "hello")] and not model.busy)
    model.setHandsFree(False, False, False)
    wait_until(lambda: not model.handsFree)
    close_preview(engine)


def test_handsfree_wake_and_website_confirmation_are_connected():
    from vox.agent.groq_tools import GroqRegistry
    from vox.agent.tools import ToolResult
    from vox.ui.app import create_live
    from vox.voice.service import Outcome

    class Backend:
        def __init__(self):
            self.calls = []

        def open_app(self, name):
            raise AssertionError("not expected")

        def open_website(self, url):
            self.calls.append(url)
            return ToolResult(ok=True, evidence="Fake browser action completed.")

    class Services:
        def __init__(self):
            self.backend = Backend()
            self.registry = GroqRegistry(self.backend)
            self.processed = []

        def engine_mode(self):
            return "legacy"

        def process_audio(self, wav, dry_run, cancelled):
            self.processed.append(wav)
            action = self.registry.plan(
                {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "open_website",
                                "arguments": '{"url":"https://example.com/"}',
                            },
                        }
                    ]
                }
            )
            return Outcome(pending=action, transcript="Open example dot com")

        def speak(self, text, cancelled):
            pass

    app = QGuiApplication.instance() or QGuiApplication([])
    engine, model = create_live(app)
    services = Services()
    wake_gate = handsfree_harness(model, services)
    root = engine.rootObjects()[0]
    speak = root.findChild(QObject, "speak")
    speak.setProperty("checked", False)
    toggle = root.findChild(QObject, "handsFreeToggle")
    approve = root.findChild(QObject, "approveButton")
    assert toggle is not None and approve is not None
    # Nothing may be captured or processed before the wake phrase.
    assert QMetaObject.invokeMethod(toggle, "toggle")
    wait_until(lambda: model.handsFree and model.state == "wake")
    wait(150)
    assert services.processed == [] and services.backend.calls == []
    wake_gate.set()
    wait_until(lambda: model.approvalPending)
    wake_gate.clear()
    assert model.wakeHeard == "hi box"
    assert not model.recording and model.transcript == "Open example dot com"
    assert "https://example.com/" in model.approvalText
    assert services.backend.calls == []
    assert QMetaObject.invokeMethod(approve, "clicked")
    wait_until(lambda: services.backend.calls == ["https://example.com/"] and not model.busy)
    model.setHandsFree(False, False, False)
    wait_until(lambda: not model.handsFree)
    close_preview(engine)


def test_live_engine_toggle_approval_history_and_repeat_are_wired():
    import threading

    from vox.agent.groq_tools import GroqRegistry
    from vox.agent.tools import ToolResult
    from vox.engine.pipeline import TurnOutcome
    from vox.ui.app import create_live

    class Backend:
        def open_app(self, name):
            raise AssertionError("not expected")

        def open_website(self, url):
            raise AssertionError("the fake live service must not execute a browser action")

    class Services:
        def __init__(self):
            self.backend = Backend()
            self.registry = GroqRegistry(self.backend)
            self.mode = "legacy"
            self.live_requests = []
            self.live_thread_id = 0
            self.approvals = []
            self.history = []
            self.pending = self.registry.plan(
                {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "open_website",
                                "arguments": '{"url":"https://example.com/"}',
                            },
                        }
                    ]
                }
            )

        def engine_mode(self):
            return self.mode

        def set_engine_mode(self, mode):
            self.mode = "live" if mode == "live" else "legacy"
            return self.mode

        def submit(self, text, dry_run, cancelled):
            raise AssertionError("legacy submit must not run in live mode")

        def live_submit(self, text, dry_run, cancelled, *, speak):
            self.live_thread_id = threading.get_ident()
            self.live_requests.append((text, dry_run, speak))
            if text == "repeat that":
                self.history = [
                    "user: open the example website",
                    "assistant: Fake browser action completed.",
                    "user: repeat that",
                ]
                return TurnOutcome(
                    kind="completed",
                    spoken="Fake browser action completed.",
                    standalone="repeat that",
                )
            self.history = [
                "user: open the example website",
                "tool: open_website awaiting approval",
            ]
            return TurnOutcome(
                kind="pending_approval",
                pending_action=self.pending,
                standalone="open the example website",
            )

        def live_approve(self, approved):
            self.approvals.append(approved)
            self.history = [
                "user: open the example website",
                "assistant: Fake browser action completed.",
            ]
            return TurnOutcome(
                kind="completed",
                spoken="Fake browser action completed.",
                results=[ToolResult(ok=True, evidence="Fake browser action completed.")],
                standalone="open the example website",
            )

        def live_deny(self):
            raise AssertionError("deny is not part of this flow")

        def live_history_lines(self, limit=8):
            return self.history[-limit:]

        def speak(self, text, cancelled):
            pass

    app = QGuiApplication.instance() or QGuiApplication([])
    engine, model = create_live(app)
    services = Services()
    model._services = services
    model.changed.emit()
    wait(25)

    root = engine.rootObjects()[0]
    live_toggle = root.findChild(QObject, "liveEngineToggle")
    input_field = root.findChild(QObject, "requestInput")
    speak = root.findChild(QObject, "speak")
    run = root.findChild(QObject, "runButton")
    approve = root.findChild(QObject, "approveButton")
    repeat = root.findChild(QObject, "repeatLastButton")
    understood = root.findChild(QObject, "understoodText")
    history = root.findChild(QObject, "liveHistoryList")
    assert all(
        item is not None
        for item in (live_toggle, input_field, speak, run, approve, repeat, understood, history)
    )

    assert model.engineMode == "legacy"
    assert live_toggle.property("checked") is False
    assert QMetaObject.invokeMethod(live_toggle, "toggle")
    wait_until(lambda: model.engineMode == "live" and live_toggle.property("checked") is True)

    speak.setProperty("checked", False)
    input_field.setProperty("text", "open Example")
    assert QMetaObject.invokeMethod(run, "clicked")
    wait_until(lambda: model.approvalPending and not model.busy)

    assert services.live_requests == [("open Example", False, False)]
    assert services.live_thread_id != threading.get_ident()
    assert services.approvals == []
    assert "https://example.com/" in model.approvalText
    assert model.lastStandalone == "open the example website"
    assert understood.property("visible") is True
    assert understood.property("text") == "Understood: open the example website"
    assert model.liveHistory == services.history
    assert history.property("count") == len(services.history)

    assert QMetaObject.invokeMethod(approve, "clicked")
    wait_until(
        lambda: (
            services.approvals == [True]
            and not model.busy
            and not model.approvalPending
            and model.status == "Fake browser action completed."
        )
    )

    assert repeat.property("visible") is True
    assert QMetaObject.invokeMethod(repeat, "clicked")
    wait_until(lambda: len(services.live_requests) == 2 and not model.busy)
    assert services.live_requests[-1] == ("repeat that", False, True)
    assert model.status == "Fake browser action completed."
    assert model.liveHistory == services.history
    close_preview(engine)
