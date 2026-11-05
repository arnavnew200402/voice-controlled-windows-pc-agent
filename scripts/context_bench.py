"""LE2 bench: glossary WER delta + contextualiser code-vs-auto A/B.

Honest scope: the "LLM" in the auto arm is an *oracle* scripted to return
the expected JSON for cases the code path marks unresolved. That measures
routing correctness and code-path latency/coverage — not the accuracy of
any real small model (none is available in this sandbox; the real-model
A/B lands with the LE4 pipeline and is recorded in docs/MODEL_BENCH.md).
Output: artifacts/live_engine/context_bench.json
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vox.engine.clock import VirtualClock
from vox.engine.context import CodeContextualiser, Contextualiser, DesktopSnapshot
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary, word_error_rate

WER_CORPUS: list[tuple[str, str]] = [
    ("open Notepad", "open no pad"),
    ("open Visual Studio Code", "open vs code"),
    ("open Chrome", "open crow"),
    ("open FileExplorer", "open file explorer"),
    ("open MediaPlayer", "open media player"),
    ("open Calculator", "open calculater"),
    ("open Calendar", "open calender"),
    ("open Notepad++", "open notepad plus plus"),
    ("open Chrome and search lofi", "open crow and search lofi"),
    ("type in Notepad", "type in no pad"),
    ("open Edge", "open microsoft edge"),
    ("scroll down", "scroll down"),  # control: untouched speech
    ("close the window", "close the window"),
    ("open Word", "open word"),
]


def wer_section() -> dict[str, Any]:
    glossary = Glossary()
    before = [word_error_rate(intended, heard) for intended, heard in WER_CORPUS]
    after = [word_error_rate(intended, glossary.repair(heard)[0]) for intended, heard in WER_CORPUS]
    return {
        "corpus": len(WER_CORPUS),
        "mean_wer_without_glossary": round(statistics.fmean(before), 3),
        "mean_wer_with_glossary": round(statistics.fmean(after), 3),
        "remaining_errors": [
            heard
            for (intended, heard), score in zip(WER_CORPUS, after, strict=True)
            if score > 0 and intended != glossary.repair(heard)[0]
        ],
    }


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))] if ordered else 0.0


# (setup_key, utterance, last_command, expected_standalone_fragment)
AB_CASES: list[tuple[str, str, str | None, str]] = [
    ("windows", "close it", None, "Chrome — Docs"),
    ("windows", "close the other one", None, "Chrome — Video"),
    ("windows", "make it bigger", None, "Chrome — Docs"),
    ("plain", "open no pad", None, "open Notepad"),
    ("plain", "open calculator", None, "open Calculator"),
    ("redo", "do that again", None, "open Calculator"),
    ("plain", "volume thoda kam karo", None, "volume thoda kam karo"),
    ("correction", "no I said Notepad++", "open Notepad", "open Notepad++"),
    ("empty", "close it", None, "close the window 'Untitled'"),  # needs the oracle
    ("plain", "open chrome and", None, "open Chrome and"),
]


def build_registry(setup: str) -> tuple[EntityRegistry, DesktopSnapshot]:
    registry = EntityRegistry(VirtualClock())
    snap = DesktopSnapshot()
    if setup == "windows":
        docs = registry.register("window", "Chrome — Docs")
        registry.register("window", "Chrome — Video")
        snap = DesktopSnapshot(focused_window_id=docs.id, focused_title=docs.label)
    if setup == "redo":
        registry.register_action("open Calculator", evidence="Calculator opened.")
    return registry, snap


def ab_section(reps: int = 50) -> dict[str, Any]:
    code_hits = auto_hits = 0
    latencies: list[float] = []
    misses: list[str] = []
    oracle_calls = 0

    def oracle(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal oracle_calls
        oracle_calls += 1
        return {
            "turn_kind": "refinement",
            "standalone_command": "close the window 'Untitled'",
            "references": [{"mention": "it", "kind": "window", "resolved_id": None}],
            "confidence": 0.9,
        }

    for setup, utterance, last_command, fragment in AB_CASES:
        registry, snap = build_registry(setup)
        code = CodeContextualiser(registry, Glossary())
        start = time.perf_counter()
        for _ in range(reps):
            result = code.contextualise(utterance, snapshot=snap, last_command=last_command)
        latencies.append((time.perf_counter() - start) * 1000 / reps)
        if fragment.lower() in result.standalone_command.lower():
            code_hits += 1
        else:
            misses.append(utterance)
        registry, snap = build_registry(setup)
        auto = Contextualiser(CodeContextualiser(registry, Glossary()), llm=oracle)
        result = auto.contextualise(utterance, snapshot=snap, last_command=last_command)
        if fragment.lower() in result.standalone_command.lower():
            auto_hits += 1
    total = len(AB_CASES)
    return {
        "cases": total,
        "code_only_accuracy": round(code_hits / total, 3),
        "auto_with_oracle_llm_accuracy": round(auto_hits / total, 3),
        "oracle_calls": oracle_calls,
        "code_misses": misses,
        "code_latency_ms": {
            "p50": round(pct(latencies, 0.5), 3),
            "p95": round(pct(latencies, 0.95), 3),
        },
        "note": "Oracle LLM = scripted perfect answers; measures routing, not a real model.",
    }


def main() -> None:
    report = {
        "phase": "LE2",
        "environment": "Linux sandbox, no model/key; oracle-scripted LLM arm",
        "wer": wer_section(),
        "contextualiser_ab": ab_section(),
    }
    output = Path("artifacts/live_engine/context_bench.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
