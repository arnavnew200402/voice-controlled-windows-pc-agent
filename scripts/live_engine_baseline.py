"""LE0 baseline measurements for the Live Command Engine (legacy path).

Measures only what this sandbox can measure honestly — no microphone, no
Groq key, no network, and no Vosk model download (alphacephei.com is not
reachable from here). Everything else is recorded under ``not_measured``
with the reason, never estimated. Output: artifacts/live_engine/baseline.json
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vox.agent.groq import GroqClient
from vox.agent.groq_tools import GroqRegistry
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.voice.audio import frame_rms
from vox.voice.wake import contains_wake_phrase


class BenchBackend:
    """Instant fake desktop backend; records calls, touches nothing."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        def method(*args: object, **kwargs: object) -> ToolResult:
            self.calls.append(name)
            return ToolResult(ok=True, evidence=f"{name} done.")

        return method

    def resolve_folder(self, target: str) -> Path:
        return Path("/tmp")

    def list_windows(self) -> list[object]:
        return []


def tool_message(name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "tool_calls": [
            {
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ]
    }


# (utterance, tool, args, mode) — mode "run" = plan(+approve)+execute on the
# fake backend; "plan" = plan-timing only (execute needs window/file binding
# that the legacy UI supplies interactively).
REPLAY: list[tuple[str, str, dict[str, object], str]] = [
    ("open notepad", "open_app", {"name": "Notepad"}, "run"),
    ("open calculator", "open_app", {"name": "Calculator"}, "run"),
    ("open paint", "open_app", {"name": "Paint"}, "run"),
    ("open the browser", "open_app", {"name": "Browser"}, "run"),
    ("open settings", "open_app", {"name": "Settings"}, "run"),
    ("open file explorer", "open_app", {"name": "FileExplorer"}, "run"),
    ("open calendar", "open_app", {"name": "Calendar"}, "run"),
    ("open photos", "open_app", {"name": "Photos"}, "run"),
    ("what are my pc specs", "system_info", {}, "run"),
    ("how much disk space is left", "system_info", {}, "run"),
    ("system info", "system_info", {}, "run"),
    ("tell me about this computer", "system_info", {}, "run"),
    ("open example dot com", "open_website", {"url": "https://example.com/"}, "run"),
    ("go to wikipedia", "open_website", {"url": "https://www.wikipedia.org/"}, "run"),
    ("open github", "open_website", {"url": "https://github.com/"}, "run"),
    ("open the news site", "open_website", {"url": "https://example.org/news"}, "run"),
    ("copy hello world to clipboard", "set_clipboard", {"text": "hello world"}, "run"),
    ("put my email on the clipboard", "set_clipboard", {"text": "me@example.com"}, "run"),
    ("copy this code", "set_clipboard", {"text": "print(42)"}, "run"),
    ("take a screenshot", "screenshot", {}, "run"),
    ("screenshot this", "screenshot", {}, "run"),
    ("open downloads folder", "open_folder", {"target": "Downloads"}, "plan"),
    ("open documents", "open_folder", {"target": "Documents"}, "plan"),
    ("type hello in notepad", "type_text", {"text": "hello"}, "plan"),
    ("scroll down", "scroll", {"amount": -5}, "plan"),
    ("minimize this window", "minimize_window", {}, "plan"),
    ("maximize chrome", "maximize_window", {}, "plan"),
    ("close this window", "close_window", {}, "plan"),
    (
        "copy report to documents",
        "copy_file",
        {"source": r"C:\Users\test\a.txt", "destination": r"C:\Users\test\b.txt"},
        "plan",
    ),
    ("delete the old file", "delete_file", {"path": r"C:\Users\test\old.txt"}, "plan"),
]

WAKE_POSITIVES = [
    "hi vox",
    "Hi Vox",
    "hey vox",
    "Hi Vox open chrome",
    "okay vox",
    "ok vox",
    "hi box",
    "hey box",
    "hi fox",
    "hey fox",
    "high vox",
    "i vox",
    "hey walks",
    "hi wax",
    "hivox",
    "um hi vox please",
    "hai vox",
    "hi folks",
    "hey vaux",
    "okay voss",
]
WAKE_NEGATIVES = [
    "the weather is nice today",
    "a box of chocolates",
    "i walks every day",
    "say hi to the fox",
    "hey there box",
    "vox media published an article",
    "open the box please",
    "high five everyone",
    "the fox jumps over the dog",
    "okay let's start the meeting",
    "hi everyone welcome back",
    "this podcast is brought to you by squarespace",
    "volume up please",
    "what time is it there",
    "walking in the park",
    "the inbox is full",
    "hey guys what's up",
    "a high wall",
    "fox news at nine",
    "ok google set a timer",
]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def stage_stats(values_ms: list[float]) -> dict[str, float]:
    return {
        "n": len(values_ms),
        "p50_ms": round(pct(values_ms, 0.50), 3),
        "p95_ms": round(pct(values_ms, 0.95), 3),
        "mean_ms": round(statistics.fmean(values_ms), 3) if values_ms else 0.0,
    }


def replay_legacy(runs: int = 3) -> dict[str, Any]:
    plan_ms: list[float] = []
    execute_ms: list[float] = []
    errors = 0
    executed = 0
    for _ in range(runs):
        for _utterance, tool, args, mode in REPLAY:
            registry = GroqRegistry(BenchBackend())  # type: ignore[arg-type]
            start = time.perf_counter()
            try:
                action = registry.plan(tool_message(tool, args))
            except ProviderError:
                errors += 1
                continue
            plan_ms.append((time.perf_counter() - start) * 1000)
            if mode != "run":
                continue
            start = time.perf_counter()
            if action.tier.name != "SAFE":
                approval = registry.request_approval(action)
                registry.resolve_approval(approval, True)
                result = registry.execute(action, approval)
            else:
                result = registry.execute(action)
            execute_ms.append((time.perf_counter() - start) * 1000)
            executed += 1 if result.ok else 0
    return {
        "commands": len(REPLAY),
        "runs": runs,
        "plan_errors": errors,
        "executed_ok": executed,
        "plan": stage_stats(plan_ms),
        "approve_plus_execute_fake_backend": stage_stats(execute_ms),
        "note": "Local overhead only (validate/plan/approve/dispatch to an instant "
        "fake backend). Excludes mic capture, network STT/chat/TTS and real "
        "desktop actions — none are measurable in this sandbox. plan_errors are "
        "folder/file items whose binding checks the real (Windows) filesystem, "
        "absent here; they are covered by tests/test_groq_voice.py fixtures.",
    }


def request_payload() -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class CaptureTransport:
        def post(self, path: str, data: bytes, content_type: str, limit: int) -> bytes:
            captured["body"] = json.loads(data)
            return json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": ""},
                        }
                    ]
                }
            ).encode()

    registry = GroqRegistry(BenchBackend())  # type: ignore[arg-type]
    schemas = registry.schemas()
    GroqClient(CaptureTransport()).chat("open calculator", schemas)
    body = captured["body"]
    return {
        "messages_count": len(body["messages"]),
        "roles": [m["role"] for m in body["messages"]],
        "includes_prior_turns": len(body["messages"]) > 2,
        "stream": body["stream"],
        "tool_schemas_count": len(body["tools"]),
        "request_bytes": len(json.dumps(body).encode()),
        "system_prompt_chars": len(body["messages"][0]["content"]),
    }


def wake_matcher_text() -> dict[str, Any]:
    missed = [t for t in WAKE_POSITIVES if not contains_wake_phrase(t)]
    false_accepts = [t for t in WAKE_NEGATIVES if contains_wake_phrase(t)]
    return {
        "level": "text matcher only (contains_wake_phrase); NOT audio FA/FR",
        "positives": len(WAKE_POSITIVES),
        "missed": missed,
        "false_reject_rate": round(len(missed) / len(WAKE_POSITIVES), 3),
        "negatives": len(WAKE_NEGATIVES),
        "false_accepts": false_accepts,
        "false_accept_rate": round(len(false_accepts) / len(WAKE_NEGATIVES), 3),
    }


def idle_matcher_cost(seconds: float = 3.0) -> dict[str, Any]:
    frame = b"\x10\x00" * 4000  # one 250 ms int16 frame
    rss_kb = 0
    status = Path("/proc/self/status")
    if status.exists():
        for line in status.read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    frames = 0
    while time.perf_counter() - wall_start < seconds:
        frame_rms(frame)
        contains_wake_phrase("the quick brown fox jumps")
        frames += 1
        time.sleep(0.25)  # idle loop is frame-paced in production
    cpu = time.process_time() - cpu_start
    wall = time.perf_counter() - wall_start
    return {
        "scope": "frame_rms + wake text matcher at 4 fps; EXCLUDES Vosk inference",
        "frames": frames,
        "cpu_pct_of_one_core": round(100 * cpu / wall, 3),
        "process_rss_mb": round(rss_kb / 1024, 1),
    }


def main() -> None:
    baseline: dict[str, Any] = {
        "phase": "LE0",
        "path": "legacy",
        "environment": "Linux sandbox, fake backend/transport, no mic/key/network",
        "measured": {
            "legacy_replay": replay_legacy(),
            "llm_request": request_payload(),
            "wake_matcher_text": wake_matcher_text(),
            "idle_matcher_cost": idle_matcher_cost(),
        },
        "not_measured": [
            {
                "metric": "wake audio false-accept/false-reject",
                "reason": "Vosk model host (alphacephei.com) unreachable from sandbox; "
                "no microphone. Scheduled: Windows `vox bench --wake` in LE1b "
                "with the model bundled by CI.",
            },
            {
                "metric": "idle detector CPU/RAM incl. Vosk inference",
                "reason": "Same as above; only the pure-Python matcher share is measured.",
            },
            {
                "metric": "STT/chat/TTS latencies (Groq)",
                "reason": "No API key in sandbox; providers stubbed per autonomy contract.",
            },
            {
                "metric": "end-of-speech to action-complete on a real desktop",
                "reason": "Linux sandbox has no Windows desktop; physical validation "
                "is the checklist in docs/WINDOWS_TEST_CHECKLIST.md.",
            },
        ],
    }
    output = Path("artifacts/live_engine/baseline.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(baseline, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
