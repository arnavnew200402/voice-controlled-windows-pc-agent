"""Live per-turn pipeline (spec 4.4), behind engine.mode=live.

Flow: control plane → contextualise → retrieval + prompt v2 assembly →
streaming chat → early SAFE dispatch through the existing GroqRegistry
(tiers and single-use argument-bound approvals unchanged) → sentence-
chunked speech → ledger/timeline/checkpoint. Meta-tools
(ask_clarification/stay_silent/show_card) are intercepted here and never
reach the backend registry, which would fail closed on those names.
Voice approval remains unwired: CONFIRM actions return a pending outcome
for the existing click-approval UI (LE decisions, 2026-11-05).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from vox.agent.groq import StreamDone, StreamEvent, TextDelta, ToolCallComplete
from vox.agent.groq_tools import GroqRegistry, PlannedAction
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.approvals import Tier
from vox.engine.acks import ack_phrase, should_ack
from vox.engine.clock import Clock, SystemClock
from vox.engine.config import EngineSettings
from vox.engine.context import (
    Contextualiser,
    DesktopSnapshot,
    PendingClarification,
    TurnKind,
)
from vox.engine.control import ControlAction, classify_control
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary, words
from vox.engine.ledger import ActionsLedger
from vox.engine.memory import PreferencesSheet, SessionStore, UserCard
from vox.engine.prompt_assembly import META_TOOL_NAMES, META_TOOL_SCHEMAS, assemble_prompt
from vox.engine.retrieval import DeviceIndex
from vox.engine.timeline import Timeline
from vox.engine.turns import CommitGuard, GenerationToken, Turn, TurnManager
from vox.events import Contextualized, LatencySample, ToolFinished, ToolStarted

MAX_TRANSCRIPT_CHARS = 8000
_DICTATION_CUES = ("dictate", "type this", "type out", "write this", "likho", "likh do")
_REPEAT_PHRASES = {"repeat", "repeat that", "say that again", "phir se bolo", "phirse bolo"}
_SENTENCE_RE = re.compile(r"[^.!?।]+[.!?।]+(?:\s+|$)|[^.!?।]+$")


class StreamClient(Protocol):
    def chat_stream(
        self, messages: list[dict[str, str]], schemas: list[dict[str, object]]
    ) -> Iterator[StreamEvent]: ...


@dataclass
class TurnOutcome:
    kind: Literal[
        "completed",
        "pending_approval",
        "clarification",
        "silent",
        "card",
        "dictation",
        "status",
        "cancelled",
        "error",
    ]
    spoken: str = ""
    results: list[ToolResult] = field(default_factory=list)
    pending_action: PlannedAction | None = None
    clarification: PendingClarification | None = None
    card: tuple[str, str] | None = None
    dictation_text: str = ""
    standalone: str = ""
    turn_kind: TurnKind = TurnKind.NEW_COMMAND
    control_action: str | None = None


class LivePipeline:
    def __init__(
        self,
        *,
        registry: GroqRegistry,
        client: StreamClient,
        timeline: Timeline,
        manager: TurnManager,
        contextualiser: Contextualiser,
        entities: EntityRegistry,
        glossary: Glossary,
        ledger: ActionsLedger,
        user_card: UserCard,
        preferences: PreferencesSheet,
        index: DeviceIndex | None = None,
        store: SessionStore | None = None,
        settings: EngineSettings | None = None,
        clock: Clock | None = None,
        speaker: Callable[[str], None] | None = None,
        summary: str = "",
        habits: dict[str, str] | None = None,
    ) -> None:
        self._registry = registry
        self._client = client
        self._timeline = timeline
        self._manager = manager
        self._guard = CommitGuard(manager)
        self._contextualiser = contextualiser
        self._entities = entities
        self._glossary = glossary
        self._ledger = ledger
        self._user_card = user_card
        self._preferences = preferences
        self._index = index
        self._store = store
        self._settings = settings or EngineSettings()
        self._clock = clock or SystemClock()
        self._speaker = speaker or (lambda _sentence: None)
        self._summary = summary
        self._habits = habits or {}
        self._schemas = [*registry.schemas(), *META_TOOL_SCHEMAS]
        self._pending_clarification: PendingClarification | None = None
        self._pending_action: tuple[PlannedAction, str, Turn] | None = None
        self._last_command: str | None = None
        self.mic_muted = False

    # -- public surface -------------------------------------------------------

    @property
    def pending_action(self) -> PlannedAction | None:
        return self._pending_action[0] if self._pending_action else None

    def repeat_last(self) -> str | None:
        for event in reversed(self._timeline.events()):
            if event.speaker == "assistant" and event.kind == "final" and event.text:
                return event.text
        return None

    def answer_status(self) -> str:
        active = self._manager.active
        last = self._ledger.last(1)
        evidence = last[0].evidence if last else ""
        if active is not None and active.committed:
            return f"I'm working on it. Last step: {evidence or 'just started'}"
        if self._pending_action is not None:
            return "I'm waiting for your approval on the card."
        if evidence:
            return f"I'm idle. Last thing I did: {evidence}"
        return "I'm idle."

    def run_turn(
        self,
        transcript: str,
        *,
        trigger: str = "typed",
        asr_confidence: float | None = None,
        snapshot: DesktopSnapshot | None = None,
        dry_run: bool = False,
    ) -> TurnOutcome:
        turn = self._manager.open_turn(trigger)
        self._manager.add_fragment(turn, transcript, asr_confidence)
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            self._manager.cancel(turn, "too_long")
            return TurnOutcome(kind="error", spoken="That was too long for me to process.")

        control = classify_control(transcript, approval_pending=False)
        if control is not None:
            if control.action is ControlAction.STOP:
                self._deny_pending()
                self._manager.cancel(turn, "stop_word")
                return TurnOutcome(kind="cancelled", control_action="stop")
            if control.action is ControlAction.STATUS:
                spoken = self.answer_status()
                self._speak(turn, [spoken])
                self._manager.close(turn)
                return TurnOutcome(kind="status", spoken=spoken)
            if control.action is ControlAction.MUTE:
                self.mic_muted = True
                self._manager.close(turn)
                return TurnOutcome(
                    kind="completed",
                    spoken="Microphone off. Use the toggle to resume.",
                    control_action="mute",
                )

        dictation = self._dictation_text(transcript)
        if dictation is not None:
            self._manager.hard_end(turn)
            self._manager.close(turn)
            return TurnOutcome(
                kind="dictation", dictation_text=dictation, turn_kind=TurnKind.NEW_COMMAND
            )

        if " ".join(words(transcript)) in _REPEAT_PHRASES:
            last = self.repeat_last() or "There is nothing to repeat yet."
            self._manager.hard_end(turn)
            self._speak(turn, [last])
            self._manager.close(turn)
            return TurnOutcome(kind="completed", spoken=last)

        started = self._clock.monotonic()
        pending_before = self._pending_clarification
        ctx = self._contextualiser.contextualise(
            transcript,
            snapshot=snapshot,
            pending=pending_before,
            last_command=self._last_command,
        )
        self._latency(turn, "contextualise", started)
        if ctx.turn_kind is TurnKind.CLARIFICATION_ANSWER:
            self._pending_clarification = None
        self._timeline.append_event(
            Contextualized(
                turn_id=turn.id,
                standalone=ctx.standalone_command,
                refs=tuple(r.resolved_id for r in ctx.references if r.resolved_id),
            ),
            turn_id=turn.id,
        )
        self._timeline.append("system", "state_note", "prompt_version=v2", turn_id=turn.id)

        if ctx.needs_clarification and ctx.pending is not None:
            self._pending_clarification = ctx.pending
            self._manager.hard_end(turn)
            self._speak(turn, [ctx.pending.question])
            self._manager.close(turn)
            self._checkpoint()
            return TurnOutcome(
                kind="clarification",
                spoken=ctx.pending.question,
                clarification=ctx.pending,
                standalone=ctx.standalone_command,
                turn_kind=ctx.turn_kind,
            )

        self._manager.hard_end(turn)
        return self._execute_turn(
            turn, ctx.standalone_command, transcript, dry_run=dry_run, turn_kind=ctx.turn_kind
        )

    def approve_pending(self, approved: bool) -> TurnOutcome | None:
        """Click-approval resolution — the only approval channel (LE policy)."""
        if self._pending_action is None:
            return None
        action, approval_id, turn = self._pending_action
        self._pending_action = None
        self._registry.resolve_approval(approval_id, approved)
        if not approved:
            self._speak(turn, ["Okay, cancelled."])
            self._manager.close(turn)
            self._checkpoint()
            return TurnOutcome(kind="completed", spoken="Okay, cancelled.")
        result = self._guard.dispatch(
            self._manager.token(turn),
            side_effecting=True,
            run=lambda: self._dispatch(turn, action, approval_id),
        )
        self._speak(turn, [result.evidence])
        self._manager.close(turn)
        self._checkpoint()
        return TurnOutcome(kind="completed", spoken=result.evidence, results=[result])

    # -- internals --------------------------------------------------------------

    def _dictation_text(self, transcript: str) -> str | None:
        toks = words(transcript)
        joined = " ".join(toks)
        for cue in _DICTATION_CUES:
            if joined == cue or joined.startswith(cue + " "):
                raw = transcript.strip()
                # Strip the cue words from the raw text, keep the rest verbatim.
                parts = raw.split(None, len(cue.split()))
                return parts[-1] if len(parts) > len(cue.split()) else ""
        return None

    def _deny_pending(self) -> None:
        if self._pending_action is not None:
            _action, approval_id, turn = self._pending_action
            self._registry.resolve_approval(approval_id, False)
            self._pending_action = None
            if turn.state not in {"closed", "cancelled"}:
                self._manager.cancel(turn, "stop_word")

    def _execute_turn(
        self,
        turn: Turn,
        standalone: str,
        raw: str,
        *,
        dry_run: bool,
        turn_kind: TurnKind = TurnKind.NEW_COMMAND,
    ) -> TurnOutcome:
        retrieval_started = self._clock.monotonic()
        hits = self._index.search(standalone, k=6) if self._index is not None else []
        self._latency(turn, "retrieval", retrieval_started)
        assembled = assemble_prompt(
            user_card=self._user_card,
            preferences=self._preferences,
            ledger=self._ledger,
            timeline=self._timeline,
            summary=self._summary,
            habits=self._habits,
            glossary_terms=tuple(self._glossary.canonicals()),
            retrieved=hits,
            settings={"ack_already_played": False, "dry_run": dry_run},
            standalone_command=standalone,
            raw_utterance=raw,
        )
        state = _StreamState()
        try:
            self._run_stream(turn, assembled.messages, state, dry_run=dry_run)
            if (
                state.results
                and not dry_run  # dry runs speak their evidence, never a follow-up
                and not state.spoken
                and not state.pending
                and not state.silent
                and state.card is None
            ):
                ack = ack_phrase("working", "en")
                if should_ack(
                    tools_planned=len(state.results),
                    already_spoken=False,
                    ack_already_played=False,
                ):
                    self._speak(turn, [ack])
                    state.spoken.append(ack)
                follow_up = [
                    *assembled.messages,
                    {
                        "role": "user",
                        "content": "<tool_results>\n"
                        + "\n".join(r.evidence for r in state.results)
                        + "\n</tool_results>",
                    },
                ]
                self._run_stream(turn, follow_up, state, dry_run=dry_run, follow_up=True)
        except ProviderError:
            self._manager.cancel(turn, "provider_error")
            self._checkpoint()
            return TurnOutcome(
                kind="error",
                spoken="The voice service is unavailable right now.",
                standalone=standalone,
            )

        if not state.spoken and state.results and not state.silent:
            evidence = "; ".join(r.evidence for r in state.results)
            self._speak(turn, [evidence])
            state.spoken.append(evidence)
        if state.spoken:
            self._manager.record_assistant_speech(turn, " ".join(state.spoken))
        self._last_command = standalone
        if state.pending is not None:
            action, approval_id = state.pending
            self._pending_action = (action, approval_id, turn)
            self._checkpoint()
            return TurnOutcome(
                kind="pending_approval",
                turn_kind=turn_kind,
                spoken=" ".join(state.spoken),
                results=state.results,
                pending_action=action,
                standalone=standalone,
            )
        self._manager.close(turn)
        self._checkpoint()
        if state.silent:
            return TurnOutcome(kind="silent", standalone=standalone)
        if state.clarification is not None:
            return TurnOutcome(
                kind="clarification",
                spoken=state.clarification.question,
                clarification=state.clarification,
                results=state.results,
                standalone=standalone,
            )
        if state.card is not None:
            return TurnOutcome(
                kind="card",
                spoken=" ".join(state.spoken),
                card=state.card,
                results=state.results,
                standalone=standalone,
            )
        return TurnOutcome(
            kind="completed",
            spoken=" ".join(state.spoken),
            results=state.results,
            standalone=standalone,
            turn_kind=turn_kind,
        )

    def _run_stream(
        self,
        turn: Turn,
        messages: list[dict[str, str]],
        state: _StreamState,
        *,
        dry_run: bool,
        follow_up: bool = False,
    ) -> None:
        token = self._manager.token(turn)
        stream_started = self._clock.monotonic()
        first_token_seen = False
        buffer = ""
        for event in self._client.chat_stream(messages, self._schemas):
            if not first_token_seen and not isinstance(event, StreamDone):
                first_token_seen = True
                self._latency(turn, "ttft", stream_started)
            if isinstance(event, TextDelta):
                buffer += event.text
                sentences, buffer = self._drain_sentences(buffer)
                if sentences:
                    self._speak(turn, sentences)
                    state.spoken.extend(sentences)
            elif isinstance(event, ToolCallComplete):
                self._handle_tool_call(turn, token, event, state, dry_run=dry_run)
        if buffer.strip():
            self._speak(turn, [buffer.strip()])
            state.spoken.append(buffer.strip())

    @staticmethod
    def _drain_sentences(buffer: str) -> tuple[list[str], str]:
        sentences: list[str] = []
        consumed = 0
        for match in _SENTENCE_RE.finditer(buffer):
            sentence = match.group(0).strip()
            if match.end() == len(buffer) and not sentence.endswith((".", "!", "?", "।")):
                break  # trailing fragment: keep buffering
            if sentence:
                sentences.append(sentence)
            consumed = match.end()
        return sentences, buffer[consumed:]

    def _handle_tool_call(
        self,
        turn: Turn,
        token: GenerationToken,
        call: ToolCallComplete,
        state: _StreamState,
        *,
        dry_run: bool,
    ) -> None:
        if call.name in META_TOOL_NAMES:
            self._handle_meta(turn, call, state)
            return
        if state.pending is not None or state.silent:
            return  # nothing else runs after a pending approval / silence
        try:
            action = self._registry.plan(
                {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments},
                        }
                    ]
                }
            )
        except ProviderError:
            state.results.append(ToolResult(ok=False, evidence="That action is not available."))
            return
        if dry_run:
            state.results.append(
                ToolResult(
                    ok=True,
                    simulated=True,
                    evidence="Dry run: " + action.description + " No action was performed.",
                )
            )
            return
        if action.tier == Tier.CONFIRM:
            approval_id = self._registry.request_approval(action)
            state.pending = (action, approval_id)
            return
        result = self._guard.dispatch(
            token, side_effecting=True, run=lambda: self._dispatch(turn, action, None)
        )
        state.results.append(result)

    def _handle_meta(self, turn: Turn, call: ToolCallComplete, state: _StreamState) -> None:
        try:
            args = json.loads(call.arguments or "{}")
        except ValueError:
            return
        if not isinstance(args, dict):
            return
        if call.name == "stay_silent":
            state.silent = True
        elif call.name == "show_card":
            state.card = (str(args.get("title", "")), str(args.get("body", "")))
        elif call.name == "ask_clarification":
            choices = args.get("choices")
            options = tuple(
                (str(choice), str(choice))
                for choice in (choices if isinstance(choices, list) else [])[:3]
            )
            question = str(args.get("question", "Which one?"))
            standalone = turn.text
            pending = PendingClarification(
                question=question,
                options=options,
                command_template=f"{standalone} (clarification answer: {{choice}})",
            )
            state.clarification = pending
            self._pending_clarification = pending
            self._speak(turn, [question])
            state.spoken.append(question)

    def _dispatch(self, turn: Turn, action: PlannedAction, approval_id: str | None) -> ToolResult:
        self._timeline.append_event(
            ToolStarted(name=action.name, title=action.description), turn_id=turn.id
        )
        result = self._registry.execute(action, approval_id)
        self._timeline.append_event(
            ToolFinished(name=action.name, ok=result.ok, evidence_summary=result.evidence),
            turn_id=turn.id,
        )
        record = self._ledger.record(
            turn_id=turn.id,
            tool=action.name,
            ok=result.ok,
            evidence=result.evidence,
            args_redacted=json.loads(action.args.model_dump_json()),
            target_label=_target_label(action),
        )
        if self._store is not None:
            self._store.append_action(record)
        if result.ok:
            self._entities.register_action(turn.text, evidence=result.evidence)
        return result

    def _speak(self, turn: Turn, sentences: list[str]) -> None:
        del turn
        for sentence in sentences:
            if sentence.strip():
                self._speaker(sentence.strip())

    def _latency(self, turn: Turn, stage: str, started: float) -> None:
        self._timeline.append_event(
            LatencySample(
                turn_id=turn.id,
                stage=stage,
                ms=max(0.0, (self._clock.monotonic() - started) * 1000.0),
            ),
            turn_id=turn.id,
        )

    def _checkpoint(self) -> None:
        if self._store is not None:
            self._store.checkpoint_timeline(self._timeline.events())


@dataclass
class _StreamState:
    spoken: list[str] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)
    pending: tuple[PlannedAction, str] | None = None
    silent: bool = False
    card: tuple[str, str] | None = None
    clarification: PendingClarification | None = None


def _target_label(action: PlannedAction) -> str:
    args = action.args
    for attr in ("name", "url", "path", "target", "text"):
        value = getattr(args, attr, None)
        if isinstance(value, str) and value:
            return value[:120]
    return action.name
