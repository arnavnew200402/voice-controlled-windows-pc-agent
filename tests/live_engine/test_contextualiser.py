"""LE2-C: contextualiser — edge cases 3, 10, 16, 17, 24, 25 (+ router)."""

from vox.engine.clock import VirtualClock
from vox.engine.context import (
    CodeContextualiser,
    Contextualiser,
    DesktopSnapshot,
    TurnKind,
)
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary


def make(registry=None, glossary=None, **kwargs):
    registry = registry if registry is not None else EntityRegistry(VirtualClock())
    glossary = glossary if glossary is not None else Glossary()
    return CodeContextualiser(registry, glossary, **kwargs), registry, glossary


def test_edge3_close_it_and_the_other_one_and_bigger():
    code, registry, _glossary = make()
    docs = registry.register("window", "Chrome — Docs")
    video = registry.register("window", "Chrome — Video")
    snap = DesktopSnapshot(focused_window_id=docs.id, focused_title=docs.label)

    result = code.contextualise("close it", snapshot=snap)
    assert result.turn_kind is TurnKind.REFINEMENT
    assert result.standalone_command == "close the window 'Chrome — Docs'"
    assert result.references[0].resolved_id == docs.id

    result = code.contextualise("close the other one", snapshot=snap)
    assert result.standalone_command == "close the window 'Chrome — Video'"
    assert result.references[0].resolved_id == video.id

    result = code.contextualise("make it bigger", snapshot=snap)
    assert result.standalone_command == "make the window 'Chrome — Docs' bigger"


def test_edge3_do_that_again_on_the_left_monitor():
    code, registry, _glossary = make()
    registry.register("monitor", "left Dell")
    right = registry.register("monitor", "right Dell")
    action = registry.register_action("open Calculator", evidence="Calculator opened.")
    result = code.contextualise("do that again on the left monitor")
    assert result.standalone_command == "open Calculator on the monitor 'left Dell'"
    kinds = {(ref.kind, ref.resolved_id) for ref in result.references}
    assert ("action", action.id) in kinds
    assert ("monitor", registry.by_kind("monitor")[0].id) in kinds
    assert right.id not in {ref.resolved_id for ref in result.references}


def test_edge10_asr_damage_repaired_before_standalone():
    code, _registry, _glossary = make()
    result = code.contextualise("open no pad")
    assert result.standalone_command == "open Notepad"
    assert [repair.heard for repair in result.asr_repairs] == ["no pad"]
    assert code.contextualise("open crow").standalone_command == "open Chrome"


def test_edge16_hinglish_detected_and_preserved():
    code, _registry, _glossary = make()
    result = code.contextualise("Chrome kholo aur YouTube pe lo-fi search karo")
    assert result.language == "hinglish"
    assert "Chrome" in result.standalone_command and "kholo" in result.standalone_command
    result = code.contextualise("volume thoda kam karo")
    assert result.language == "hinglish" and result.turn_kind is TurnKind.NEW_COMMAND


def test_edge17_ambiguous_app_asks_then_second_one_answers():
    code, registry, _glossary = make()
    word = registry.register("app", "Word")
    wordpad = registry.register("app", "WordPad")
    result = code.contextualise("open word")
    assert result.needs_clarification and result.pending is not None
    assert result.clarification_hint == "Word or WordPad?"
    answer = code.contextualise("the second one", pending=result.pending)
    assert answer.turn_kind is TurnKind.CLARIFICATION_ANSWER
    assert answer.standalone_command == "open WordPad"
    assert answer.references[0].resolved_id == wordpad.id
    assert answer.references[0].resolved_id != word.id


def test_edge17_second_window_by_mention_order():
    code, registry, _glossary = make()
    registry.register("window", "Chrome — Docs")
    second = registry.register("window", "Chrome — Video")
    result = code.contextualise("close the second one")
    assert result.references[0].resolved_id == second.id
    assert "Chrome — Video" in result.standalone_command


def test_edge24_correction_swaps_target_and_only_proposes_alias():
    code, _registry, glossary = make()
    result = code.contextualise("no, I said Notepad++", last_command="open Notepad")
    assert result.turn_kind is TurnKind.CORRECTION
    assert result.standalone_command == "open Notepad++"
    assert glossary.proposals() == [("notepad", "Notepad++")]
    # Not learned until confirmed.
    assert glossary.repair("open notepad")[0] == "open Notepad"


def test_edge25_language_switch_and_pinned_reply_language():
    code, _registry, _glossary = make()
    english = code.contextualise("open calculator")
    assert english.language == "en" and english.reply_language == "en"
    hindi = code.contextualise("क्रोम खोलो")
    assert hindi.language == "hi" and hindi.reply_language == "hi"
    pinned, _registry2, _glossary2 = make(pinned_reply_language="en")
    assert pinned.contextualise("क्रोम खोलो").reply_language == "en"


def test_unresolved_reference_routes_to_llm_and_hallucinated_ids_dropped():
    code, registry, _glossary = make()
    window = registry.register("window", "Untitled — Notepad")

    def fake_llm(payload):
        return {
            "addressed_to_assistant": True,
            "turn_kind": "refinement",
            "standalone_command": "close the window 'Untitled — Notepad'",
            "references": [
                {"mention": "it", "kind": "window", "resolved_id": "win-999", "candidates": []}
            ],
            "confidence": 0.9,
        }

    router = Contextualiser(code, llm=fake_llm)
    # No snapshot and the window is stale to the code path's last() it still
    # resolves — so instead clear the registry path: use an empty registry.
    empty_code, _empty_registry, _g = make()
    router = Contextualiser(empty_code, llm=fake_llm)
    result = router.contextualise("close it")
    assert result.route == "llm"
    assert result.references[0].resolved_id is None  # hallucinated id dropped
    assert result.standalone_command == "close the window 'Untitled — Notepad'"
    del window


def test_code_path_handles_resolvable_turns_without_llm():
    code, registry, _glossary = make()
    registry.register("window", "Untitled — Notepad")
    calls = []

    def fake_llm(payload):  # pragma: no cover - must not be called
        calls.append(payload)
        return {}

    router = Contextualiser(code, llm=fake_llm)
    result = router.contextualise("close it")
    assert result.route == "code" and calls == []


def test_llm_failure_falls_back_to_code_result():
    code, _registry, _glossary = make()

    def broken_llm(payload):
        raise RuntimeError("model down")

    result = Contextualiser(code, llm=broken_llm).contextualise("close it")
    assert result.route == "code"
    assert result.references and result.references[0].resolved_id is None


def test_screen_context_flag_and_kinds():
    code, _registry, _glossary = make()
    assert code.contextualise("what is this error on screen").needs_screen_context
    assert code.contextualise("open chrome and").turn_kind is TurnKind.INCOMPLETE
    assert code.contextualise("thanks").turn_kind is TurnKind.CHITCHAT
    assert code.contextualise("stop").turn_kind is TurnKind.TASK_CONTROL
