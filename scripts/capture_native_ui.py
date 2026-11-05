"""Capture synthetic Qt preview states and indicative frame intervals.

Run on the target Windows display for meaningful performance measurements. The
software/offscreen backend is useful for smoke testing, not a GPU performance gate.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow

from vox.ui.app import close_preview, create_preview
from vox.ui.model import STATES


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    output = Path("artifacts/ui/native")
    output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    engine, model = create_preview(app)
    root = engine.rootObjects()[0]
    notch = root.findChild(QQuickWindow, "notchWindow")
    if notch is None:
        raise RuntimeError("Notch window missing")
    # Child windows may be initially hidden until their parent is exposed.
    wait(500)
    if not root.grabWindow().save(str(output / "studio.png")):
        raise RuntimeError("Could not capture studio")
    measurements = {}
    for state in STATES:
        frames: list[float] = []
        times: list[float] = []

        def on_frame(times: list[float] = times) -> None:
            times.append(time.perf_counter())

        notch.frameSwapped.connect(on_frame)
        timer = QTimer()
        timer.timeout.connect(notch.requestUpdate)
        timer.start(16)
        model.selectState(state)
        wait(700)
        timer.stop()
        notch.frameSwapped.disconnect(on_frame)
        frames = [(b - a) * 1000 for a, b in pairwise(times)]
        ordered = sorted(frames)
        measurements[state] = {
            "samples": len(frames),
            "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2) if ordered else None,
            "max_ms": round(max(frames), 2) if frames else None,
        }
        image = notch.grabWindow()
        if image.isNull() or not image.save(str(output / f"{state}.png")):
            raise RuntimeError(f"Could not capture {state}")
    # Capture the wired approval flow as well as the static design states.
    model.startDemo("delete")
    limit = time.monotonic() + 5
    while not model.approvalPending and time.monotonic() < limit:
        wait(25)
    if not model.approvalPending:
        raise RuntimeError("Sandbox approval did not appear")
    wait(350)
    if not root.grabWindow().save(str(output / "studio-sandbox-approval.png")):
        raise RuntimeError("Could not capture sandbox studio")
    if not notch.grabWindow().save(str(output / "notch-sandbox-approval.png")):
        raise RuntimeError("Could not capture sandbox approval")
    model.resolveDemo(False)
    limit = time.monotonic() + 5
    while model.busy and time.monotonic() < limit:
        wait(25)
    if model.busy:
        raise RuntimeError("Sandbox denial did not finish")
    report = {
        "note": "Frame-swapped intervals in this environment, not a Windows GPU performance gate.",
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", "default"),
        "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", "default"),
        "states": measurements,
    }
    (output / "frame-intervals.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    # Destroy the engine before the context object so QML never sees a dead model.
    close_preview(engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
