import queue
import time

from vox.demo.worker import DemoWorker
from vox.events import ApprovalRequested, StateChanged, ToolFinished


def test_stop_preempts_waiting_sandbox_action():
    worker = DemoWorker(step_delay=0.01)
    try:
        worker.start("delete")
        deadline = time.monotonic() + 2
        requested = False
        while time.monotonic() < deadline and not requested:
            event = worker.events.get(timeout=1)
            requested = isinstance(event, ApprovalRequested)
        assert requested
        worker.stop()
        received = []
        while time.monotonic() < deadline:
            try:
                event = worker.events.get(timeout=0.5)
            except queue.Empty:
                break
            received.append(event)
            if isinstance(event, StateChanged) and event.state == "idle":
                break
        assert any(isinstance(e, StateChanged) and e.state == "idle" for e in received)
        assert not any(isinstance(e, ToolFinished) for e in received)
    finally:
        worker.close()
    assert not worker.alive()
