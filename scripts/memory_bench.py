"""LE3 bench: retrieval latency, session checkpoint/restore, layer sizes.

Targets (spec §2/4.5): retrieval + snapshot p95 ≤ 100 ms (proceed without
past 150 ms); user card ≈400 tokens, preferences ≈300. Local sandbox
timings — real Tier-B numbers come from the Windows bench.
Output: artifacts/live_engine/memory_bench.json
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vox.engine.clock import VirtualClock
from vox.engine.ledger import ActionsLedger
from vox.engine.memory import PreferencesSheet, SessionStore, UserCard, approx_tokens
from vox.engine.retrieval import DeviceIndex
from vox.engine.timeline import Timeline

QUERIES = ["notepad", "chrome docs", "project folder", "krom", "budget", "left monitor"]


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))] if ordered else 0.0


def retrieval_section(sizes: tuple[int, ...] = (200, 1000, 5000)) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for size in sizes:
        index = DeviceIndex()
        index.index_apps(["Notepad", "Calculator", "Chrome", "Photos"])
        index.index_windows([f"Window {i} — App{i % 37} budget chrome docs" for i in range(size)])
        index.index_folders({f"project folder {i}": f"D:\\p{i}" for i in range(size // 4)})
        latencies: list[float] = []
        for _ in range(5):
            for query in QUERIES:
                start = time.perf_counter()
                index.search(query, k=6)
                latencies.append((time.perf_counter() - start) * 1000)
        out[str(len(index))] = {
            "p50_ms": round(pct(latencies, 0.5), 3),
            "p95_ms": round(pct(latencies, 0.95), 3),
        }
    return out


def checkpoint_section(events: int = 500, actions: int = 100) -> dict[str, Any]:
    clock = VirtualClock()
    timeline = Timeline(clock)
    for index in range(events):
        timeline.append("user", "partial", f"utterance {index}", turn_id=f"turn-{index // 5}")
    ledger = ActionsLedger(clock)
    records = [
        ledger.record(
            turn_id="turn-1", tool="open_app", ok=True, evidence="done", target_label=f"App{i}"
        )
        for i in range(actions)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp))
        start = time.perf_counter()
        store.checkpoint_timeline(timeline.events())
        for record in records:
            store.append_action(record)
        checkpoint_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        restored = store.restore()
        restore_ms = (time.perf_counter() - start) * 1000
        store.close()
    return {
        "events": events,
        "actions": actions,
        "checkpoint_ms": round(checkpoint_ms, 2),
        "restore_ms": round(restore_ms, 2),
        "restored_events": len(restored.timeline),
        "restored_actions": len(restored.actions),
    }


def sizes_section() -> dict[str, Any]:
    card = UserCard(
        name="Asha Example",
        languages=("en", "hi"),
        default_browser="Chrome",
        search_engine="Google",
        monitor_layout="left = laptop, right = Dell 27 inch",
    )
    prefs = PreferencesSheet(
        named_locations={
            "my project folder": "D:\\work\\vox",
            "tax docs": "D:\\finance\\tax",
            "music": "C:\\Users\\me\\Music",
        },
        default_apps={"browser": "Chrome", "editor": "Visual Studio Code"},
        monitor_per_app={"Chrome": "right Dell"},
        do_not_touch=("D:\\private",),
    )
    return {
        "user_card_approx_tokens": approx_tokens(card.render()),
        "user_card_budget": 400,
        "preferences_approx_tokens": approx_tokens(prefs.render()),
        "preferences_budget": 300,
    }


def main() -> None:
    report = {
        "phase": "LE3",
        "environment": "Linux sandbox timings (not Tier-B hardware)",
        "retrieval_by_index_size": retrieval_section(),
        "checkpoint_restore": checkpoint_section(),
        "layer_sizes": sizes_section(),
    }
    output = Path("artifacts/live_engine/memory_bench.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
