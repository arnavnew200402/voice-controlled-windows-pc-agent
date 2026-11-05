"""Non-blocking worker for the in-memory walkthrough; never runs real tools."""

from __future__ import annotations

import queue
import threading
import time
from typing import Literal

from vox.demo.engine import DemoEngine, Scenario
from vox.events import DemoEvent, Reply, StateChanged

Command = tuple[Literal["start", "resolve"], Scenario | bool]


class DemoWorker:
    def __init__(self, *, step_delay: float = 0.7) -> None:
        self.events: queue.Queue[DemoEvent] = queue.Queue()
        self._commands: queue.Queue[Command] = queue.Queue()
        self._stop = threading.Event()
        self._shutdown = threading.Event()
        self._step_delay = step_delay
        self._thread = threading.Thread(target=self._run, name="sandbox-demo", daemon=True)
        self._thread.start()

    def start(self, scenario: Scenario) -> None:
        self._commands.put(("start", scenario))

    def resolve(self, approve: bool) -> None:
        self._commands.put(("resolve", approve))

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self._shutdown.set()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            raise RuntimeError("Sandbox worker did not stop")

    def alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        try:
            self._run_loop()
        except Exception:  # noqa: BLE001 - isolate failures from the UI
            # No exception text: the production error/audit pipeline is not built.
            self.events.put(StateChanged(state="error", reason="Sandbox worker failed"))
            self.events.put(Reply(text="Simulation failed. No real PC actions were performed."))
            self.events.put(StateChanged(state="idle", reason="Simulation ended"))

    def _run_loop(self) -> None:
        engine = DemoEngine(self.events.put)
        deadline = time.monotonic() + self._step_delay
        while not self._shutdown.is_set():
            if self._stop.is_set():
                self._stop.clear()
                while True:
                    try:
                        self._commands.get_nowait()
                    except queue.Empty:
                        break
                engine.stop()
                continue
            try:
                command, value = self._commands.get(timeout=0.025)
                if self._stop.is_set() or self._shutdown.is_set():
                    continue
                if command == "start" and value in ("open", "delete"):
                    engine.start(value)
                    deadline = time.monotonic() + self._step_delay
                elif command == "resolve" and type(value) is bool:
                    engine.resolve(value)
                    deadline = time.monotonic() + self._step_delay
            except queue.Empty:
                pass
            if time.monotonic() >= deadline and not self._stop.is_set():
                engine.advance()
                deadline = time.monotonic() + self._step_delay
