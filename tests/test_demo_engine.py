"""The demo never opens a real application or touches the filesystem."""

from vox.approvals import ApprovalStore
from vox.demo.engine import DemoEngine
from vox.events import ApprovalRequested, ApprovalResolved, Reply, StateChanged, ToolFinished


def test_open_sandbox_emits_verified_evidence():
    events = []
    engine = DemoEngine(events.append)
    assert engine.start("open")
    assert not engine.start("delete")
    engine.advance()
    engine.advance()
    assert engine.virtual_apps == {"Notepad"}
    assert any(isinstance(e, ToolFinished) and e.ok for e in events)
    assert any(isinstance(e, Reply) and not e.spoken and "Virtual" in e.text for e in events)
    engine.advance()
    assert engine.phase == "idle"


def test_delete_requires_bound_single_use_approval():
    events = []
    engine = DemoEngine(events.append)
    assert engine.start("delete")
    engine.advance()
    assert len(engine.virtual_downloads) == 3
    requested = next(e for e in events if isinstance(e, ApprovalRequested))
    assert engine.resolve(False)
    assert len(engine.virtual_downloads) == 3
    assert not engine.resolve(True)
    assert any(isinstance(e, ApprovalResolved) and e.id == requested.id for e in events)
    engine.advance()
    assert engine.start("delete")
    engine.advance()
    assert engine.resolve(True)
    engine.advance()
    assert engine.virtual_downloads == []
    assert any(isinstance(e, ToolFinished) and e.ok for e in events)
    assert not engine.resolve(True)


def test_changed_snapshot_and_stop_prevent_execution():
    engine = DemoEngine(lambda event: None)
    engine.start("delete")
    engine.advance()
    assert engine.resolve(True)
    engine.virtual_downloads[0] = "changed"
    engine.advance()
    assert len(engine.virtual_downloads) == 3
    engine.advance()
    engine.start("delete")
    engine.advance()
    engine.stop()
    assert not engine.resolve(True)
    engine.advance()
    assert len(engine.virtual_downloads) == 3


def test_stop_after_approval_revokes_before_action():
    events = []
    engine = DemoEngine(events.append)
    engine.start("delete")
    engine.advance()
    engine.resolve(True)
    engine.stop()
    engine.advance()
    assert len(engine.virtual_downloads) == 3
    assert isinstance(events[-1], StateChanged) and events[-1].state == "idle"
    assert not any(isinstance(e, ToolFinished) for e in events)


def test_expired_sandbox_approval_never_changes_state():
    events = []
    now = [10.0]
    engine = DemoEngine(events.append)
    engine.approvals = ApprovalStore(monotonic=lambda: now[0])
    engine.start("delete")
    engine.advance()
    now[0] += 15
    assert not engine.resolve(True)
    engine.advance()
    assert len(engine.virtual_downloads) == 3
    assert any(isinstance(e, ApprovalResolved) and e.decision == "expired" for e in events)


def test_sandbox_does_not_open_sockets(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    engine = DemoEngine(lambda event: None)
    engine.start("delete")
    engine.advance()
    engine.resolve(True)
    engine.advance()
    assert engine.virtual_downloads == []
