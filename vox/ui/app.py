"""Launch the visual-only Qt Quick studio."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from shiboken6 import delete

from vox.ui.model import NotchDemoModel

if TYPE_CHECKING:
    from vox.ui.groq_model import GroqViewModel


def create_preview(app: QGuiApplication) -> tuple[QQmlApplicationEngine, NotchDemoModel]:
    # Keep Python-owned objects alive for the lifetime of the QML engine.
    model = NotchDemoModel()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("viewModel", model)
    engine.load(str(Path(__file__).parent / "qml" / "PreviewConsole.qml"))
    if not engine.rootObjects():
        raise RuntimeError("Could not load the notch preview QML")
    root = engine.rootObjects()[0]
    notch = root.findChild(QQuickWindow, "notchWindow")
    screen = app.primaryScreen()
    if notch is None or screen is None:
        raise RuntimeError("Could not find the notch window or primary screen")

    def position_notch() -> None:
        area = screen.availableGeometry()
        notch.setPosition(area.x() + (area.width() - notch.width()) // 2, area.y())

    position_notch()
    screen.availableGeometryChanged.connect(position_notch)
    # PySide wrappers must live as long as their QML objects.
    engine._preview_root = root
    engine._preview_notch = notch
    engine._position_callback = position_notch
    engine._preview_screen = screen
    engine._demo_model = model
    return engine, model


def close_preview(engine: QQmlApplicationEngine) -> None:
    """Destroy QML before its Python-owned context object and disconnect callbacks."""
    engine._demo_model.shutdown()  # type: ignore[attr-defined]
    engine._preview_screen.availableGeometryChanged.disconnect(engine._position_callback)  # type: ignore[attr-defined]
    delete(engine._preview_root)  # type: ignore[attr-defined]
    delete(engine)


def run_demo() -> int:
    app = QGuiApplication(sys.argv[:1])
    engine, model = create_preview(app)
    try:
        return app.exec()
    finally:
        close_preview(engine)
        # Model must outlive QML teardown.
        del model


def create_live(app: QGuiApplication) -> tuple[QQmlApplicationEngine, GroqViewModel]:
    from vox.ui.groq_model import GroqViewModel

    model = GroqViewModel()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("viewModel", model)
    engine.load(str(Path(__file__).parent / "qml" / "AgentWindow.qml"))
    if not engine.rootObjects():
        raise RuntimeError("Could not load the online preview QML")
    root = engine.rootObjects()[0]
    notch = root.findChild(QQuickWindow, "notchWindow")
    screen = app.primaryScreen()
    if notch is None or screen is None:
        raise RuntimeError("Could not find the notch window or primary screen")

    def position_notch() -> None:
        area = screen.availableGeometry()
        notch.setPosition(area.x() + (area.width() - notch.width()) // 2, area.y())

    position_notch()
    screen.availableGeometryChanged.connect(position_notch)
    engine._preview_root = root
    engine._preview_notch = notch
    engine._position_callback = position_notch
    engine._preview_screen = screen
    engine._demo_model = model
    return engine, model


def run_live() -> int:
    app = QGuiApplication(sys.argv[:1])
    engine, model = create_live(app)
    try:
        return app.exec()
    finally:
        close_preview(engine)
        del model
