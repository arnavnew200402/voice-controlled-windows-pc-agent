"""LE3-B: user card, preferences, session store (edge 12/21, L-03)."""

from vox.engine.clock import VirtualClock
from vox.engine.entities import EntityRegistry
from vox.engine.ledger import ActionsLedger
from vox.engine.memory import (
    PreferencesSheet,
    SessionMemory,
    SessionStore,
    UserCard,
    approx_tokens,
)
from vox.engine.timeline import Timeline
from vox.events import ToolFinished, ToolStarted


def test_user_card_and_preferences_roundtrip(tmp_path):
    card = UserCard(name="Asha", pinned_language="hi", monitor_layout="left laptop, right Dell")
    card.save(tmp_path)
    loaded = UserCard.load(tmp_path)
    assert loaded.name == "Asha" and loaded.pinned_language == "hi"
    rendered = loaded.render()
    assert "Hi Vox" in rendered and "right Dell" in rendered
    assert approx_tokens(rendered) <= 400

    prefs = PreferencesSheet(
        named_locations={"my project folder": "D:\\work\\vox"},
        default_apps={"browser": "Chrome"},
        do_not_touch=("D:\\private",),
    )
    prefs.save(tmp_path)
    loaded_prefs = PreferencesSheet.load(tmp_path)
    assert loaded_prefs.resolve_location("My Project Folder") == "D:\\work\\vox"
    assert "Do not touch" in loaded_prefs.render()
    assert UserCard.load(tmp_path / "missing").name == ""  # corrupt/missing is safe


def test_habits_are_proposals_until_confirmed():
    memory = SessionMemory()
    memory.propose_habit("second screen means", "monitor 2", turn_id="turn-3")
    assert memory.habits() == {}
    assert memory.confirm_habit("second screen means") is True
    assert memory.habits() == {"second screen means": "monitor 2"}


def _populated_timeline(clock):
    timeline = Timeline(clock)
    timeline.append("user", "final", "open secret plans", turn_id="turn-1")
    timeline.append_event(ToolStarted(name="open_app", title="Open Notepad"), turn_id="turn-1")
    timeline.append_event(
        ToolFinished(name="open_app", ok=True, evidence_summary="Notepad opened."),
        turn_id="turn-1",
    )
    timeline.append_event(ToolStarted(name="delete_file", title="Delete"), turn_id="turn-1")
    return timeline


def test_edge21_restore_marks_unfinished_tools_unknown_and_no_approvals(tmp_path):
    clock = VirtualClock()
    store = SessionStore(tmp_path, store_transcripts=True)
    store.checkpoint_timeline(_populated_timeline(clock).events())
    ledger = ActionsLedger(clock)
    record = ledger.record(
        turn_id="turn-1",
        tool="open_app",
        ok=True,
        evidence="Notepad opened.",
        target_label="Notepad",
    )
    store.append_action(record)
    registry = EntityRegistry(clock)
    window = registry.register("window", "Untitled — Notepad")
    store.snapshot_entities(registry.by_kind("window"))
    store.close()

    restored = SessionStore(tmp_path).restore()  # "crash": brand-new instance
    assert len(restored.timeline) == 4
    assert restored.unknown_tools == ["delete_file"]  # started, never finished
    assert restored.pending_approvals == ()  # expired by construction
    assert [action.tool for action in restored.actions] == ["open_app"]
    assert restored.entities[0].id == window.id


def test_transcripts_only_persisted_on_opt_in(tmp_path):
    clock = VirtualClock()
    private = SessionStore(tmp_path / "off", store_transcripts=False)
    private.checkpoint_timeline(_populated_timeline(clock).events())
    restored = private.restore()
    user_events = [e for e in restored.timeline if e.speaker == "user"]
    assert user_events and user_events[0].text == ""  # L-03: no transcript text
    assert restored.unknown_tools == ["delete_file"]  # audit trail intact

    opted = SessionStore(tmp_path / "on", store_transcripts=True)
    opted.checkpoint_timeline(_populated_timeline(clock).events())
    assert opted.restore().timeline[0].text == "open secret plans"


def test_delete_session_data_wipes_store(tmp_path):
    store = SessionStore(tmp_path, store_transcripts=True)
    store.checkpoint_timeline(_populated_timeline(VirtualClock()).events())
    assert store.counts()["timeline"] == 4
    store.delete_session_data()
    assert store.counts() == {"timeline": 0, "actions": 0, "entities": 0}
    assert store.restore().timeline == []


def test_edge12_ledger_contradiction_and_empty_undo():
    ledger = ActionsLedger(VirtualClock())
    assert ledger.last_undoable() is None  # "undo" with nothing to undo
    assert ledger.target_state("report.txt") == "unknown"
    ledger.record(
        turn_id="turn-1",
        tool="delete_file",
        ok=True,
        evidence="Deleted report.txt.",
        target_label="C:\\Users\\me\\report.txt",
    )
    assert ledger.target_state("report.txt") == "deleted"
    ledger.record(
        turn_id="turn-2",
        tool="copy_file",
        ok=True,
        evidence="Copied report.txt.",
        target_label="report.txt",
        undo_info={"tool": "delete_file"},
    )
    assert ledger.target_state("report.txt") == "acted_on"
    undoable = ledger.last_undoable()
    assert undoable is not None and undoable.tool == "copy_file"
    ledger.mark_undone(undoable.action_id)
    assert ledger.last_undoable() is None
