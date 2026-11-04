"""LE4 bench: prompt assembly, cache-prefix stability, and pipeline timing.

Honest scope: this sandbox has no Groq key, microphone, TTS device, or
Windows desktop. Assembly and local pipeline timings therefore use a
scripted streaming client and fake desktop backend. TTFT scenarios use a
``VirtualClock``: the scripted stream advances virtual time before its
first event, and the bench checks that the pipeline's own TTFT sample and
early tool dispatch observe that virtual delay. Provider prompt-cache
hit-rate is **not measured** here; only byte-stability of the static
prefix and offline parsing of Groq's usage/cache fields are verified.

Output: artifacts/live_engine/pipeline_bench.json
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vox.agent.groq import (
    GroqClient,
    StreamDone,
    StreamEvent,
    StreamUsage,
    TextDelta,
    ToolCallComplete,
)
from vox.agent.groq_tools import GroqRegistry
from vox.agent.tools import ToolResult
from vox.agent.windows_control import WindowRef
from vox.engine.clock import SystemClock, VirtualClock
from vox.engine.context import CodeContextualiser, Contextualiser
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary
from vox.engine.ledger import ActionsLedger
from vox.engine.memory import PreferencesSheet, UserCard
from vox.engine.pipeline import LivePipeline
from vox.engine.prompt_assembly import BUDGET_CHARS, PROMPT_VERSION, assemble_prompt
from vox.engine.retrieval import Chunk, ScoredChunk
from vox.engine.timeline import Timeline
from vox.engine.turns import TurnManager
from vox.events import LatencySample


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))] if ordered else 0.0


def latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(pct(values, 0.5), 3),
        "p95_ms": round(pct(values, 0.95), 3),
        "max_ms": round(max(values), 3) if values else 0.0,
    }


def prompt_kwargs(
    *,
    standalone_command: str = "close the window 'Chrome — Docs'",
    raw_utterance: str = "close it",
    desktop_lines: tuple[str, ...] = ("focused: Chrome — Docs (age 1s)",),
    summary: str = "The user is reviewing browser documents.",
) -> dict[str, Any]:
    clock = VirtualClock()
    timeline = Timeline(clock)
    for index in range(3):
        turn_id = f"turn-{index + 1}"
        timeline.append("user", "final", f"open document {index + 1}", turn_id=turn_id)
        timeline.append(
            "assistant",
            "final",
            f"Document {index + 1} is open.",
            turn_id=turn_id,
        )

    ledger = ActionsLedger(clock)
    for index in range(4):
        ledger.record(
            turn_id=f"turn-{index + 1}",
            tool="open_app",
            ok=True,
            evidence=f"Application {index + 1} opened.",
            target_label=f"App {index + 1}",
        )

    retrieved = [
        ScoredChunk(
            chunk=Chunk(
                id=f"window:{index}",
                source="window",
                title=f"Chrome — Document {index}",
                text="focused browser window",
            ),
            score=1.0 - index * 0.05,
        )
        for index in range(6)
    ]
    return {
        "user_card": UserCard(
            name="Asha Example",
            languages=("en", "hi"),
            default_browser="Chrome",
            search_engine="Google",
            monitor_layout="laptop left, external monitor right",
        ),
        "preferences": PreferencesSheet(
            named_locations={"my project folder": "D:\\work\\vox"},
            default_apps={"browser": "Chrome", "editor": "Visual Studio Code"},
            monitor_per_app={"Chrome": "right monitor"},
            do_not_touch=("D:\\private",),
        ),
        "ledger": ledger,
        "timeline": timeline,
        "summary": summary,
        "habits": {"second screen means": "right monitor"},
        "glossary_terms": ("Notepad", "Chrome", "Visual Studio Code", "Calculator"),
        "desktop_lines": desktop_lines,
        "retrieved": retrieved,
        "task_stack_lines": ("Review the open document",),
        "settings": {"ack_already_played": False, "dry_run": False},
        "standalone_command": standalone_command,
        "raw_utterance": raw_utterance,
    }


def assembly_section(reps: int = 300) -> dict[str, Any]:
    baseline_kwargs = prompt_kwargs()
    baseline = assemble_prompt(**baseline_kwargs)

    for _ in range(20):
        assemble_prompt(**baseline_kwargs)

    latencies: list[float] = []
    for _ in range(reps):
        started = time.perf_counter()
        assemble_prompt(**baseline_kwargs)
        latencies.append((time.perf_counter() - started) * 1000)

    variants = [
        prompt_kwargs(),
        prompt_kwargs(
            standalone_command="open Notepad",
            raw_utterance="open notepad",
            desktop_lines=("focused: Notepad (age 0s)",),
            summary="The user switched to note taking.",
        ),
        prompt_kwargs(
            standalone_command="open Calculator",
            raw_utterance="calculator kholo",
            desktop_lines=("focused: Calculator (age 2s)",),
            summary="The user is checking a calculation.",
        ),
        prompt_kwargs(
            standalone_command="close the other window",
            raw_utterance="dusra wala band karo",
            desktop_lines=("focused: Chrome — Video (age 0s)",),
            summary="The user is comparing two browser windows.",
        ),
    ]
    assembled_variants = [assemble_prompt(**kwargs) for kwargs in variants]
    hashes = {
        hashlib.sha256(prompt.static_prefix.encode()).hexdigest() for prompt in assembled_variants
    }

    return {
        "prompt_version": PROMPT_VERSION,
        "repetitions": reps,
        "assembly_latency": latency_summary(latencies),
        "static_prefix_bytes": baseline.static_prefix_bytes,
        "baseline_total_bytes": baseline.total_bytes,
        "static_share_of_baseline": round(baseline.static_prefix_bytes / baseline.total_bytes, 3),
        "dynamic_variants": len(assembled_variants),
        "unique_static_prefix_hashes": len(hashes),
        "static_prefix_byte_stable": len(hashes) == 1,
        "static_prefix_sha256": next(iter(hashes)) if len(hashes) == 1 else None,
        "variant_total_bytes_range": [
            min(prompt.total_bytes for prompt in assembled_variants),
            max(prompt.total_bytes for prompt in assembled_variants),
        ],
        "baseline_section_chars": baseline.sections,
        "budgeted_sections_within_limits": all(
            baseline.sections.get(key, 0) <= limit
            for key, limit in BUDGET_CHARS.items()
            if key in baseline.sections
        ),
    }


class FakeBackend:
    """DesktopBackend double: only open_app is exercised by this bench."""

    def __init__(self, clock: VirtualClock | SystemClock) -> None:
        self._clock = clock
        self.calls: list[tuple[str, str]] = []
        self.call_times: list[float] = []

    def open_app(self, name: str) -> ToolResult:
        self.calls.append(("open_app", name))
        self.call_times.append(self._clock.monotonic())
        return ToolResult(ok=True, evidence=f"{name} opened.")

    def _unused(self, name: str) -> ToolResult:
        self.calls.append((name, ""))
        return ToolResult(ok=False, evidence="Not used by pipeline bench.")

    def open_website(self, url: str) -> ToolResult:
        del url
        return self._unused("open_website")

    def resolve_folder(self, target: str) -> str:
        del target
        return "/tmp"

    def open_folder(self, path: str) -> ToolResult:
        del path
        return self._unused("open_folder")

    def list_windows(self) -> list[WindowRef]:
        return []

    def type_text(self, target: WindowRef, text: str) -> ToolResult:
        del target, text
        return self._unused("type_text")

    def scroll(self, target: WindowRef, amount: int) -> ToolResult:
        del target, amount
        return self._unused("scroll")

    def minimize(self, target: WindowRef) -> ToolResult:
        del target
        return self._unused("minimize_window")

    def maximize(self, target: WindowRef) -> ToolResult:
        del target
        return self._unused("maximize_window")

    def restore(self, target: WindowRef) -> ToolResult:
        del target
        return self._unused("restore_window")

    def close_window(self, target: WindowRef) -> ToolResult:
        del target
        return self._unused("close_window")

    def copy_file(self, source: str, destination: str) -> ToolResult:
        del source, destination
        return self._unused("copy_file")

    def move_file(self, source: str, destination: str) -> ToolResult:
        del source, destination
        return self._unused("move_file")

    def delete_file(self, path: str) -> ToolResult:
        del path
        return self._unused("delete_file")

    def screenshot(self, path: str) -> ToolResult:
        del path
        return self._unused("screenshot")

    def set_clipboard(self, text: str) -> ToolResult:
        del text
        return self._unused("set_clipboard")

    def system_info(self) -> ToolResult:
        return self._unused("system_info")


class VirtualDelayClient:
    """Advances virtual time before the first streamed event."""

    def __init__(self, clock: VirtualClock, backend: FakeBackend, delay_s: float) -> None:
        self._clock = clock
        self._backend = backend
        self._delay_s = delay_s
        self.stream_started_at: float | None = None
        self.dispatched_before_next_event = False

    def chat_stream(
        self, messages: list[dict[str, str]], schemas: list[dict[str, object]]
    ) -> Iterator[StreamEvent]:
        del messages, schemas
        self.stream_started_at = self._clock.monotonic()
        self._clock.advance(self._delay_s)
        yield ToolCallComplete(name="open_app", arguments=json.dumps({"name": "Calculator"}))
        # The generator resumes only after LivePipeline has consumed the
        # completed tool call. A backend call at this point proves dispatch
        # happened before the next stream event, not at stream end.
        self.dispatched_before_next_event = self._backend.calls == [("open_app", "Calculator")]
        self._clock.advance(0.01)
        yield TextDelta("Calculator is open.")
        yield StreamDone(finish_reason="stop")


class ImmediateTextClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat_stream(
        self, messages: list[dict[str, str]], schemas: list[dict[str, object]]
    ) -> Iterator[StreamEvent]:
        del messages, schemas
        self.calls += 1
        yield TextDelta("Done now.")
        yield StreamDone(finish_reason="stop")


class ImmediateToolClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat_stream(
        self, messages: list[dict[str, str]], schemas: list[dict[str, object]]
    ) -> Iterator[StreamEvent]:
        del messages, schemas
        self.calls += 1
        if self.calls == 1:
            yield ToolCallComplete(name="open_app", arguments=json.dumps({"name": "Calculator"}))
        else:
            yield TextDelta("Calculator is open.")
        yield StreamDone(finish_reason="stop")


def make_pipeline(
    client: Any,
    backend: FakeBackend,
    clock: VirtualClock | SystemClock,
) -> tuple[LivePipeline, Timeline]:
    timeline = Timeline(clock)
    entities = EntityRegistry(clock)
    glossary = Glossary()
    pipeline = LivePipeline(
        registry=GroqRegistry(backend),
        client=client,
        timeline=timeline,
        manager=TurnManager(timeline, clock),
        contextualiser=Contextualiser(CodeContextualiser(entities, glossary)),
        entities=entities,
        glossary=glossary,
        ledger=ActionsLedger(clock),
        user_card=UserCard(name="Bench User"),
        preferences=PreferencesSheet(),
        clock=clock,
        speaker=lambda _sentence: None,
    )
    return pipeline, timeline


def virtual_ttft_section() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for delay_s in (0.05, 0.12, 0.2):
        clock = VirtualClock()
        backend = FakeBackend(clock)
        client = VirtualDelayClient(clock, backend, delay_s)
        pipeline, timeline = make_pipeline(client, backend, clock)
        outcome = pipeline.run_turn("open calculator")

        ttft_samples = [
            event.event.ms
            for event in timeline.events()
            if isinstance(event.event, LatencySample) and event.event.stage == "ttft"
        ]
        measured_ttft = ttft_samples[0] if ttft_samples else None
        assert client.stream_started_at is not None
        dispatch_delay_ms = (
            (backend.call_times[0] - client.stream_started_at) * 1000
            if backend.call_times
            else None
        )
        scenarios.append(
            {
                "scripted_first_event_delay_ms": round(delay_s * 1000, 3),
                "measured_virtual_ttft_ms": (
                    round(measured_ttft, 3) if measured_ttft is not None else None
                ),
                "abs_error_ms": (
                    round(abs(measured_ttft - delay_s * 1000), 3)
                    if measured_ttft is not None
                    else None
                ),
                "tool_dispatch_at_virtual_ms": (
                    round(dispatch_delay_ms, 3) if dispatch_delay_ms is not None else None
                ),
                "dispatched_before_next_stream_event": (client.dispatched_before_next_event),
                "backend_calls": len(backend.calls),
                "outcome": outcome.kind,
            }
        )

    return {
        "clock": "VirtualClock (scripted delays; not provider/network timing)",
        "scenarios": scenarios,
        "max_abs_error_ms": max(
            float(scenario["abs_error_ms"])
            for scenario in scenarios
            if scenario["abs_error_ms"] is not None
        ),
        "all_dispatched_before_next_stream_event": all(
            scenario["dispatched_before_next_stream_event"] for scenario in scenarios
        ),
    }


def local_pipeline_section(reps: int = 50) -> dict[str, Any]:
    text_latencies: list[float] = []
    text_completed = 0
    for _ in range(reps):
        clock = SystemClock()
        client = ImmediateTextClient()
        pipeline, _timeline = make_pipeline(client, FakeBackend(clock), clock)
        started = time.perf_counter()
        outcome = pipeline.run_turn("say something brief")
        text_latencies.append((time.perf_counter() - started) * 1000)
        text_completed += int(outcome.kind == "completed" and client.calls == 1)

    tool_latencies: list[float] = []
    tool_completed = 0
    for _ in range(reps):
        clock = SystemClock()
        backend = FakeBackend(clock)
        tool_client = ImmediateToolClient()
        pipeline, _timeline = make_pipeline(tool_client, backend, clock)
        started = time.perf_counter()
        outcome = pipeline.run_turn("open calculator")
        tool_latencies.append((time.perf_counter() - started) * 1000)
        tool_completed += int(
            outcome.kind == "completed"
            and tool_client.calls == 2  # initial stream + one tool-evidence follow-up
            and backend.calls == [("open_app", "Calculator")]
        )

    return {
        "scope": "Local fake-provider/fake-desktop overhead; excludes network, Groq, TTS, audio, and Windows actions",
        "repetitions": reps,
        "text_only_turn": {
            **latency_summary(text_latencies),
            "completed_runs": text_completed,
        },
        "safe_tool_turn_with_follow_up": {
            **latency_summary(tool_latencies),
            "completed_runs": tool_completed,
        },
    }


class FixtureTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def post(self, path: str, data: bytes, content_type: str, limit: int) -> bytes:
        del path, data, content_type, limit
        raise AssertionError("streaming fixture must not use post()")

    def post_stream(self, path: str, data: bytes, content_type: str, limit: int) -> Iterator[bytes]:
        del path, content_type, limit
        self.requests.append(json.loads(data))
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield (
            b'data: {"choices":[],"usage":{"prompt_tokens":1200,'
            b'"completion_tokens":20,"prompt_tokens_details":'
            b'{"cached_tokens":900}}}\n\n'
        )
        yield b"data: [DONE]\n\n"


def provider_cache_section() -> dict[str, Any]:
    transport = FixtureTransport()
    events = list(
        GroqClient(transport).chat_stream([{"role": "system", "content": "static fixture"}], [])
    )
    usage = next((event for event in events if isinstance(event, StreamUsage)), None)
    return {
        "hit_rate_status": "not_measured",
        "reason": (
            "No live Groq request/key is available in this sandbox; actual "
            "prompt-cache hits require repeated provider requests."
        ),
        "offline_usage_parser_fixture": {
            "request_streamed": bool(
                transport.requests and transport.requests[0].get("stream") is True
            ),
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "cached_tokens": usage.cached_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "fields_parsed": bool(
                usage
                and usage.prompt_tokens == 1200
                and usage.cached_tokens == 900
                and usage.completion_tokens == 20
            ),
        },
    }


def main() -> None:
    report = {
        "phase": "LE4",
        "environment": "Linux sandbox; fake provider/backend; no live Groq, audio, or Windows desktop",
        "prompt_assembly": assembly_section(),
        "virtual_ttft_and_early_dispatch": virtual_ttft_section(),
        "local_pipeline_overhead": local_pipeline_section(),
        "provider_cache": provider_cache_section(),
    }
    output = Path("artifacts/live_engine/pipeline_bench.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
