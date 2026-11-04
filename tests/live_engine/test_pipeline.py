"""LE4-C: live pipeline end-to-end on scripted streams (edges 13/15/23)."""

import json

from vox.agent.groq import StreamDone, TextDelta, ToolCallComplete
from vox.agent.groq_tools import GroqRegistry
from vox.agent.tools import ToolResult
from vox.engine.clock import VirtualClock
from vox.engine.context import CodeContextualiser, Contextualiser
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary
from vox.engine.ledger import ActionsLedger
from vox.engine.memory import PreferencesSheet, UserCard
from vox.engine.pipeline import LivePipeline
from vox.engine.timeline import Timeline
from vox.engine.turns import TurnManager


class Backend:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append(name)
            return ToolResult(ok=True, evidence=f"{name} done.")

        return method

    def resolve_folder(self, target):
        from pathlib import Path

        return Path("/tmp")

    def list_windows(self):
        return []


class ScriptedClient:
    """Each chat_stream call pops the next scripted event list."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    def chat_stream(self, messages, schemas):
        self.calls.append(messages)
        events = self._scripts.pop(0) if self._scripts else [TextDelta("Done.")]
        yield from [*events, StreamDone(finish_reason="stop")]


def tool(tool_name, **args):
    return ToolCallComplete(name=tool_name, arguments=json.dumps(args))


def make_pipeline(client, *, registry=None, entities=None, ledger=None):
    clock = VirtualClock()
    timeline = Timeline(clock)
    entities = entities or EntityRegistry(clock)
    ledger = ledger or ActionsLedger(clock)
    spoken: list[str] = []
    pipeline = LivePipeline(
        registry=registry or GroqRegistry(Backend()),
        client=client,
        timeline=timeline,
        manager=TurnManager(timeline, clock),
        contextualiser=Contextualiser(CodeContextualiser(entities, Glossary())),
        entities=entities,
        glossary=Glossary(),
        ledger=ledger,
        user_card=UserCard(name="Test"),
        preferences=PreferencesSheet(),
        clock=clock,
        speaker=spoken.append,
    )
    return pipeline, spoken, timeline, ledger, entities


def test_safe_tool_dispatches_early_and_speaks_followup():
    backend = Backend()
    client = ScriptedClient(
        [
            [tool("open_app", name="Calculator")],
            [TextDelta("Calculator is open.")],
        ]
    )
    pipeline, _spoken, timeline, ledger, _e = make_pipeline(client, registry=GroqRegistry(backend))
    outcome = pipeline.run_turn("open calculator")
    assert outcome.kind == "completed"
    assert backend.calls == ["open_app"]
    assert "Calculator is open." in outcome.spoken
    assert "Working on it." in outcome.spoken  # canned ack before follow-up
    assert ledger.last(1)[0].tool == "open_app"
    kinds = [event.kind for event in timeline.events()]
    assert "tool_started" in kinds and "tool_finished" in kinds
    # The follow-up request carried the tool evidence as data.
    assert "open_app done." in client.calls[1][-1]["content"]


def test_confirm_tool_waits_for_click_approval_only():
    backend = Backend()
    client = ScriptedClient([[tool("open_website", url="https://example.com/")]])
    pipeline, _spoken, _t, ledger, _e = make_pipeline(client, registry=GroqRegistry(backend))
    outcome = pipeline.run_turn("open example dot com")
    assert outcome.kind == "pending_approval"
    assert backend.calls == []  # nothing executed yet
    assert pipeline.pending_action is not None
    # A spoken "yes" must not resolve it (click-only policy).
    pipeline.run_turn("yes")
    assert backend.calls == []
    approved = pipeline.approve_pending(True)
    assert approved is not None and backend.calls == ["open_website"]
    assert ledger.last(1)[0].ok


def test_denial_cancels_without_retry_and_stop_word_auto_denies():
    backend = Backend()
    client = ScriptedClient(
        [
            [tool("open_website", url="https://example.com/")],
            [tool("open_website", url="https://example.com/")],
        ]
    )
    pipeline, _spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    pipeline.run_turn("open example dot com")
    denied = pipeline.approve_pending(False)
    assert denied is not None and denied.spoken == "Okay, cancelled."
    assert backend.calls == []
    pipeline.run_turn("open example dot com")
    stop = pipeline.run_turn("stop")
    assert stop.kind == "cancelled" and backend.calls == []
    assert pipeline.pending_action is None  # stop word auto-denied the card


def test_meta_tools_never_reach_backend():
    backend = Backend()
    client = ScriptedClient(
        [
            [tool("ask_clarification", question="Word or WordPad?", choices=["Word", "WordPad"])],
            [TextDelta("Opening WordPad.")],
            [tool("stay_silent")],
            [tool("show_card", title="News", body="Long body"), TextDelta("Here's the news.")],
        ]
    )
    pipeline, spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    outcome = pipeline.run_turn("open the word thing")
    assert outcome.kind == "clarification" and "Word or WordPad?" in spoken
    answer = pipeline.run_turn("the second one")
    assert "clarification answer: WordPad" in answer.standalone
    assert pipeline.run_turn("just thinking aloud ignore me").kind == "silent"
    card = pipeline.run_turn("show me the news summary please")
    assert card.kind == "card" and card.card == ("News", "Long body")
    assert backend.calls == []


def test_dry_run_plans_without_dispatching():
    backend = Backend()
    client = ScriptedClient([[tool("open_app", name="Calculator")]])
    pipeline, _spoken, _t, ledger, _e = make_pipeline(client, registry=GroqRegistry(backend))
    outcome = pipeline.run_turn("open calculator", dry_run=True)
    assert outcome.kind == "completed"
    assert backend.calls == [] and ledger.records() == []
    assert "Dry run" in outcome.spoken


def test_edge13_repeat_what_did_you_do_and_do_it_again():
    backend = Backend()
    client = ScriptedClient(
        [
            [tool("open_app", name="Calculator")],
            [TextDelta("Calculator opened.")],
            [TextDelta("I opened Calculator for you.")],
            [tool("open_app", name="Calculator")],
            [TextDelta("Calculator opened.")],
        ]
    )
    pipeline, _spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    pipeline.run_turn("open calculator")
    what = pipeline.run_turn("what did you do")
    assert "I opened Calculator" in what.spoken
    # …and the ledger data was in the prompt the model answered from.
    assert "actions_ledger" in str(client.calls[2])
    repeat = pipeline.run_turn("repeat that")
    assert repeat.spoken == what.spoken.split(". ")[-1] or "I opened Calculator" in repeat.spoken
    again = pipeline.run_turn("do it again")
    assert again.kind == "completed"
    assert backend.calls == ["open_app", "open_app"]


def test_edge23_status_query_does_not_disturb_anything():
    backend = Backend()
    client = ScriptedClient([[tool("open_app", name="Calculator")], [TextDelta("Opened.")]])
    pipeline, _spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    pipeline.run_turn("open calculator")
    status = pipeline.run_turn("what are you doing")
    assert status.kind == "status" and "idle" in status.spoken.lower()
    assert backend.calls == ["open_app"]  # unchanged, no extra dispatch
    assert "open_app done." in status.spoken  # reports the last verified step


def test_edge15_dictation_is_verbatim_and_bypasses_tools():
    backend = Backend()
    client = ScriptedClient([])
    pipeline, _spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    long_text = "the quick brown fox jumps over the lazy dog " * 40
    outcome = pipeline.run_turn(f"dictate {long_text}")
    assert outcome.kind == "dictation"
    assert outcome.dictation_text.startswith("the quick brown fox")
    assert len(outcome.dictation_text) > 1500
    assert backend.calls == [] and client.calls == []


def test_sentence_chunking_speaks_incrementally():
    backend = Backend()
    client = ScriptedClient([[TextDelta("First sen"), TextDelta("tence. Second one! Tail")]])
    pipeline, spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    pipeline.run_turn("tell me something")
    assert spoken[0] == "First sentence."
    assert spoken[1] == "Second one!"
    assert spoken[-1] == "Tail"


def test_window_actions_fail_closed_until_bound_and_approved():
    from vox.agent.windows_control import WindowRef

    backend = Backend()
    client = ScriptedClient(
        [
            [tool("type_text", text="hello there")],
            [tool("type_text", text="hello there")],
        ]
    )
    pipeline, _spoken, _t, _l, _e = make_pipeline(client, registry=GroqRegistry(backend))
    outcome = pipeline.run_turn("type hello there")
    assert outcome.kind == "pending_approval"
    # No window bound: approval must refuse, never execute.
    refused = pipeline.approve_pending(True)
    assert refused is not None and refused.kind == "error"
    assert backend.calls == []
    # Bind a window (what the UI does on the approval card) → executes.
    outcome = pipeline.run_turn("type hello there")
    assert outcome.pending_action is not None
    window = WindowRef(
        hwnd=1, pid=2, created=3, focus_hwnd=1, title="Untitled", window_class="Notepad"
    )
    bound = pipeline._registry.bind_typing(outcome.pending_action, window)
    assert pipeline.rebind_pending(bound)
    done = pipeline.approve_pending(True)
    assert done is not None and done.kind == "completed"
    assert backend.calls == ["type_text"]
