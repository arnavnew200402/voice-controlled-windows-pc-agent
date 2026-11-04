"""PyInstaller entry point for the limited preview and its non-destructive smoke test."""

import sys
import traceback
from pathlib import Path


def smoke_test() -> int:
    try:
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtGui import QGuiApplication

        from vox.ui.app import close_preview, create_live

        app = QGuiApplication(sys.argv[:1])
        engine, model = create_live(app)
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()
        image = engine.rootObjects()[0].grabWindow()
        if image.isNull() or image.width() < 100:
            raise RuntimeError("Qt preview did not render")
        close_preview(engine)
        del model
        Path("vox-smoke-test.txt").write_text(
            "OK: preview window rendered without desktop actions.\n"
        )
        return 0
    except Exception:  # noqa: BLE001 - only test stack, no user data or credentials
        Path("vox-smoke-test.txt").write_text(traceback.format_exc())
        return 1


def main() -> int:
    if "--smoke-test" in sys.argv:
        return smoke_test()
    from vox.ui.app import run_live

    return run_live()


if __name__ == "__main__":
    raise SystemExit(main())
