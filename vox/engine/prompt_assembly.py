"""Cache-friendly prompt assembly (spec 4.5) + meta-tool pack (5.1).

Order: [static system v2 + user card + preferences] → [semi-static summary
+ ledger + habits + glossary] → [dynamic recent turns + desktop state +
retrieved chunks + task stack + settings + command]. The static prefix is
byte-stable for identical inputs so provider KV/prompt caches survive —
verified by test (real cache hit-rates need a live key; MODEL_BENCH).
Budgets are character approximations of the spec's token budgets (×4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vox.engine.ledger import ActionsLedger
from vox.engine.memory import PreferencesSheet, UserCard
from vox.engine.retrieval import ScoredChunk
from vox.engine.timeline import Timeline

PROMPT_VERSION = "v2"
_SYSTEM_PATH = Path(__file__).parent / "prompts" / "v2" / "system.md"

BUDGET_CHARS = {
    "user_card": 400 * 4,
    "preferences": 300 * 4,
    "summary": 250 * 4,
    "ledger": 300 * 4,
    "recent_turns": 600 * 4,
    "desktop_state": 300 * 4,
    "retrieved": 400 * 4,
}

META_TOOL_SCHEMAS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "Ask the user a short question with at most three options.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                },
                "required": ["question", "choices"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stay_silent",
            "description": "End the turn without speaking (the speech was not for you).",
            "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_card",
            "description": "Show longer content as a card; speak only a one-sentence summary.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
            },
        },
    },
]
META_TOOL_NAMES = {str(schema["function"]["name"]) for schema in META_TOOL_SCHEMAS}  # type: ignore[index]


def load_system_prompt(assistant_name: str = "Vox") -> str:
    try:
        text = _SYSTEM_PATH.read_text(encoding="utf-8")
    except OSError:
        text = "You are <ASSISTANT_NAME>, the voice of this Windows PC."
    return text.replace("<ASSISTANT_NAME>", assistant_name or "Vox")


def _clip(text: str, budget: int) -> str:
    return text if len(text) <= budget else text[:budget]


def _tag(name: str, body: str) -> str:
    return f"<{name}>\n{body}\n</{name}>" if body else ""


@dataclass(frozen=True)
class AssembledPrompt:
    messages: list[dict[str, str]]
    prompt_version: str
    static_prefix_bytes: int
    total_bytes: int
    sections: dict[str, int]

    @property
    def static_prefix(self) -> str:
        return self.messages[0]["content"] if self.messages else ""


def recent_turns_text(timeline: Timeline, *, max_turns: int = 6) -> str:
    lines: list[str] = []
    finals = [
        event
        for event in timeline.events()
        if event.kind == "final" and event.speaker in {"user", "assistant"} and event.text
    ]
    for event in finals[-max_turns * 2 :]:
        who = "user" if event.speaker == "user" else "assistant"
        lines.append(f"{who}: {event.text}")
    return _clip("\n".join(lines), BUDGET_CHARS["recent_turns"])


def assemble_prompt(
    *,
    user_card: UserCard,
    preferences: PreferencesSheet,
    ledger: ActionsLedger,
    timeline: Timeline,
    summary: str = "",
    habits: dict[str, str] | None = None,
    glossary_terms: tuple[str, ...] = (),
    desktop_lines: tuple[str, ...] = (),
    retrieved: list[ScoredChunk] | None = None,
    task_stack_lines: tuple[str, ...] = (),
    settings: dict[str, Any] | None = None,
    standalone_command: str,
    raw_utterance: str,
    screen_description: str = "",
) -> AssembledPrompt:
    sections: dict[str, int] = {}

    def section(key: str, body: str) -> str:
        clipped = _clip(body, BUDGET_CHARS.get(key, len(body)))
        sections[key] = len(clipped)
        return clipped

    static = "\n".join(
        part
        for part in (
            load_system_prompt(user_card.assistant_name),
            _tag("persona", section("user_card", user_card.render())),
            _tag("prefs", section("preferences", preferences.render())),
        )
        if part
    )
    semi = "\n".join(
        part
        for part in (
            _tag("session_summary", section("summary", summary)),
            _tag("actions_ledger", section("ledger", ledger.render(10))),
            _tag(
                "user_habits",
                "\n".join(f"{k}: {v}" for k, v in sorted((habits or {}).items())),
            ),
            _tag("glossary", ", ".join(glossary_terms)),
        )
        if part
    )
    retrieved_text = "\n".join(
        f"[{hit.chunk.id}] {hit.chunk.title} — {hit.chunk.text}".strip()
        for hit in (retrieved or [])
    )
    dynamic = "\n".join(
        part
        for part in (
            _tag("device_context", section("retrieved", retrieved_text)),
            _tag("desktop_state", section("desktop_state", "\n".join(desktop_lines))),
            _tag("recent_turns", recent_turns_text(timeline)),
            _tag("task_stack", "\n".join(task_stack_lines)),
            _tag("screen_description", screen_description),
            _tag("settings", json.dumps(settings or {}, sort_keys=True)),
        )
        if part
    )
    user_message = (
        _tag("command", standalone_command) + "\n" + _tag("raw_utterance", raw_utterance)
    ).strip()
    messages = [{"role": "system", "content": static}]
    if semi:
        messages.append({"role": "system", "content": semi})
    if dynamic:
        messages.append({"role": "system", "content": dynamic})
    messages.append({"role": "user", "content": user_message})
    return AssembledPrompt(
        messages=messages,
        prompt_version=PROMPT_VERSION,
        static_prefix_bytes=len(static.encode()),
        total_bytes=sum(len(m["content"].encode()) for m in messages),
        sections=sections,
    )
