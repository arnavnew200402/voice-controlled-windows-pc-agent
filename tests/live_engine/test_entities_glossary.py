"""LE2-A: entity registry (TTL/ordinals/other) + glossary repair/proposals."""

from vox.engine.clock import VirtualClock
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary, word_error_rate


def test_registry_ordinals_last_and_other():
    registry = EntityRegistry(VirtualClock())
    first = registry.register("window", "Chrome — Docs")
    second = registry.register("window", "Chrome — Video")
    assert registry.ordinal("window", 1) is first
    assert registry.ordinal("window", 2) is second
    assert registry.ordinal("window", 3) is None
    assert registry.last("window") is second
    assert registry.other("window", exclude_id=second.id) is first
    assert registry.other("window", exclude_id=None) is second


def test_registry_ttl_hides_stale_facts():
    clock = VirtualClock()
    registry = EntityRegistry(clock)
    old = registry.register("window", "Old window", ttl_s=10)
    registry.register("monitor", "Dell right")
    clock.advance(11)
    assert registry.last("window") is None
    assert registry.last("window", fresh_only=False) is old
    assert registry.last("monitor") is not None


def test_registry_actions_and_forget():
    registry = EntityRegistry(VirtualClock())
    action = registry.register_action("open Calculator", evidence="Calculator opened.")
    assert registry.last("action") is action
    assert action.data["evidence"] == "Calculator opened."
    registry.forget(action.id)
    assert registry.last("action") is None
    registry.register("app", "Calculator")
    registry.clear()
    assert registry.by_kind("app") == []


def test_glossary_repairs_known_asr_damage():
    glossary = Glossary()
    repaired, repairs = glossary.repair("open no pad")
    assert repaired == "open Notepad" and repairs[0].fixed == "Notepad"
    assert glossary.repair("open vs code")[0] == "open Visual Studio Code"
    assert glossary.repair("open crow")[0] == "open Chrome"
    assert glossary.repair("open file explorer")[0] == "open FileExplorer"
    assert glossary.repair("scroll down please") == ("scroll down please", [])
    assert glossary.repair("open notepad")[0] == "open Notepad"  # never Notepad++


def test_glossary_ambiguity_candidates():
    glossary = Glossary()
    assert glossary.ambiguous_matches("word") == ["Word", "WordPad"]
    assert glossary.ambiguous_matches("chrome") == ["Chrome"]
    assert glossary.ambiguous_matches("something else") == []


def test_glossary_hotwords_include_wake_and_apps():
    hotwords = Glossary().hotwords(("Hi Vox", "Hey Vox"))
    assert hotwords.startswith("Hi Vox, Hey Vox")
    assert "Notepad" in hotwords and "Visual Studio Code" in hotwords


def test_learned_entries_need_confirmation():
    glossary = Glossary()
    glossary.propose("code editor", "Visual Studio Code")
    assert glossary.repair("open code editor")[0] == "open code editor"  # not applied yet
    assert glossary.proposals() == [("code editor", "Visual Studio Code")]
    assert glossary.confirm("code editor") is True
    assert glossary.repair("open code editor")[0] == "open Visual Studio Code"
    assert glossary.confirm("code editor") is False


def test_word_error_rate_basics():
    assert word_error_rate("open notepad", "open notepad") == 0.0
    assert word_error_rate("open notepad", "open no pad") == 1.0
    assert word_error_rate("", "") == 0.0
