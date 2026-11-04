"""Contextualiser (L-01): language normalisation only — never routing.

Turns "close it", "the other one", "do that again on the left monitor"
into a standalone command using the entity registry, a desktop snapshot
and the glossary. It never picks tools, never assigns tiers, never
answers. The code path runs first (≤20 ms budget); the small-model path
(§5.2 prompt) is used only when references stay unresolved, and its
output is validated against registry ids before being trusted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from vox.engine.control import classify_control
from vox.engine.endpointing import is_dangling
from vox.engine.entities import EntityRegistry
from vox.engine.glossary import Glossary, Repair, words

PROMPT_VERSION = "v2"
_PROMPT_PATH = Path(__file__).parent / "prompts" / "v2" / "contextualiser.md"


class TurnKind(StrEnum):
    NEW_COMMAND = "new_command"
    REFINEMENT = "refinement"
    CORRECTION = "correction"
    CLARIFICATION_ANSWER = "clarification_answer"
    TASK_CONTROL = "task_control"
    RETURN_TO_EARLIER = "return_to_earlier"
    QUESTION = "question"
    CHITCHAT = "chitchat"
    NOT_FOR_ME = "not_for_me"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class Reference:
    mention: str
    kind: str
    resolved_id: str | None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class PendingClarification:
    question: str
    options: tuple[tuple[str, str], ...]  # (entity_id, label)
    command_template: str  # contains "{choice}"


@dataclass(frozen=True)
class DesktopSnapshot:
    focused_window_id: str | None = None
    focused_title: str = ""


@dataclass
class ContextResult:
    addressed_to_assistant: bool = True
    turn_kind: TurnKind = TurnKind.NEW_COMMAND
    standalone_command: str = ""
    references: tuple[Reference, ...] = ()
    task_ref: str | None = None
    needs_clarification: bool = False
    clarification_hint: str | None = None
    pending: PendingClarification | None = None
    needs_screen_context: bool = False
    language: str = "en"
    reply_language: str = "en"
    asr_repairs: tuple[Repair, ...] = ()
    confidence: float = 0.95
    route: Literal["code", "llm"] = "code"

    def needs_llm(self) -> bool:
        if self.needs_clarification:
            return False  # asking the user is the resolution
        if any(ref.resolved_id is None for ref in self.references):
            return True
        return self.confidence < 0.6


_HINGLISH_CUES = {
    "kholo",
    "khol",
    "karo",
    "kar",
    "band",
    "chahiye",
    "wala",
    "wali",
    "chalao",
    "batao",
    "lagao",
    "thoda",
    "zyada",
    "mujhe",
    "abhi",
    "jaldi",
    "mera",
    "meri",
    "nahi",
    "nahin",
    "aur",
    "phir",
    "kitna",
    "kaise",
    "kab",
    "kya",
    "matlab",
}
_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "1st": 1,
    "2nd": 2,
    "3rd": 3,
    "pehla": 1,
    "dusra": 2,
    "tisra": 3,
}
_CORRECTION_LEADS = ("no i meant", "no i said", "i meant", "i said", "mera matlab tha")
_QUESTION_STARTS = {
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "kya",
    "kitna",
    "kaise",
    "kab",
    "कितना",
}
_CHITCHAT = {"hello", "hi", "hey", "thanks", "thank", "namaste", "shukriya", "ok", "okay", "cool"}


def detect_language(text: str) -> str:
    toks = words(text)
    devanagari = any("\u0900" <= char <= "\u097f" for char in text)
    latin = any(char.isascii() and char.isalpha() for char in text)
    if devanagari:
        return "hi" if not latin else "hinglish"
    cues = sum(1 for token in toks if token in _HINGLISH_CUES)
    if cues >= 2 or (cues >= 1 and len(toks) <= 4):
        return "hinglish"
    return "en"


class CodeContextualiser:
    def __init__(
        self,
        registry: EntityRegistry,
        glossary: Glossary,
        *,
        pinned_reply_language: str | None = None,
    ) -> None:
        self._registry = registry
        self._glossary = glossary
        self._pinned = pinned_reply_language

    # -- entry point --------------------------------------------------------

    def contextualise(
        self,
        utterance: str,
        *,
        snapshot: DesktopSnapshot | None = None,
        pending: PendingClarification | None = None,
        last_command: str | None = None,
    ) -> ContextResult:
        snap = snapshot or DesktopSnapshot()
        repaired, repairs = self._glossary.repair(utterance)
        toks = words(repaired)
        result = ContextResult(
            standalone_command=repaired,
            asr_repairs=tuple(repairs),
            language=detect_language(utterance),
        )
        result.reply_language = self._reply_language(utterance, result.language)
        result.confidence = max(0.05, 0.95 - 0.05 * len(repairs))
        if not toks:
            result.turn_kind = TurnKind.INCOMPLETE
            result.confidence = 0.1
            return result

        if pending is not None and self._answer_pending(result, toks, pending):
            return result
        if self._correction(result, toks, last_command):
            return result
        if classify_control(repaired, approval_pending=False) is not None:
            result.turn_kind = TurnKind.TASK_CONTROL
            return result

        if self._app_ambiguity(result, toks):
            return result
        if not self._redo(result, toks):  # "do that again…" owns "that"
            self._resolve_references(result, toks, snap)
        self._classify_rest(result, toks, utterance)
        return result

    def _reply_language(self, utterance: str, language: str) -> str:
        if self._pinned in {"en", "hi"}:
            return self._pinned
        if language == "hi":
            return "hi"
        if language == "hinglish":
            toks = words(utterance)
            cues = sum(1 for token in toks if token in _HINGLISH_CUES)
            return "hi" if toks and cues / len(toks) >= 0.5 else "en"
        return "en"

    # -- clarification answers & corrections --------------------------------

    def _answer_pending(
        self, result: ContextResult, toks: list[str], pending: PendingClarification
    ) -> bool:
        chosen: tuple[str, str] | None = None
        for index, token in enumerate(toks):
            if token in _ORDINALS:
                position = _ORDINALS[token]
                if 1 <= position <= len(pending.options):
                    chosen = pending.options[position - 1]
                    mention = " ".join(toks[index : index + 2])
                    break
        if chosen is None:
            joined = " ".join(toks)
            for entity_id, label in pending.options:
                if " ".join(words(label)) == joined:
                    chosen = (entity_id, label)
                    mention = joined
                    break
        if chosen is None:
            return False
        entity_id, label = chosen
        result.turn_kind = TurnKind.CLARIFICATION_ANSWER
        result.standalone_command = pending.command_template.replace("{choice}", label)
        result.references = (
            Reference(mention, "app", entity_id, tuple(label for _id, label in pending.options)),
        )
        return True

    def _correction(self, result: ContextResult, toks: list[str], last_command: str | None) -> bool:
        joined = " ".join(toks)
        remainder: str | None = None
        for lead in _CORRECTION_LEADS:
            if joined == lead or joined.startswith(lead + " "):
                remainder = joined[len(lead) :].strip()
                break
        if remainder is None and toks[:1] in (["no"], ["nahi"], ["nahin"]) and len(toks) <= 4:
            remainder = " ".join(toks[1:])
        if remainder is None or not last_command:
            return False
        # The corrected target: a glossary canonical inside the remainder.
        target = None
        for canonical in sorted(self._glossary.canonicals(), key=len, reverse=True):
            if " ".join(words(canonical)) in remainder:
                target = canonical
                break
        if target is None:
            return False
        standalone = last_command
        swapped_out = None
        for canonical in sorted(self._glossary.canonicals(), key=len, reverse=True):
            if canonical != target and canonical.lower() in last_command.lower():
                position = last_command.lower().index(canonical.lower())
                standalone = (
                    last_command[:position] + target + last_command[position + len(canonical) :]
                )
                swapped_out = canonical
                break
        result.turn_kind = TurnKind.CORRECTION
        result.standalone_command = standalone
        if swapped_out is not None:
            # Proposal only — learned after explicit confirmation (L-08).
            self._glossary.propose(swapped_out.lower(), target)
        return True

    # -- ambiguity & references ----------------------------------------------

    def _app_ambiguity(self, result: ContextResult, toks: list[str]) -> bool:
        if len(toks) < 2 or toks[0] not in {"open", "launch", "start", "kholo", "chalao"}:
            return False
        phrase = " ".join(toks[1:3])
        candidates = self._glossary.ambiguous_matches(phrase) or self._glossary.ambiguous_matches(
            toks[1]
        )
        present = {entity.label: entity.id for entity in self._registry.by_kind("app")}
        options = tuple((present[name], name) for name in candidates if name in present)
        if len(options) < 2:
            return False
        verb = "open" if toks[0] in {"open", "launch", "start"} else toks[0]
        question = f"{options[0][1]} or {options[1][1]}?"
        result.needs_clarification = True
        result.clarification_hint = question
        result.pending = PendingClarification(
            question=question,
            options=options[:3],
            command_template=f"{verb} {{choice}}",
        )
        result.references = (
            Reference(phrase, "app", None, tuple(label for _id, label in options)),
        )
        result.confidence = min(result.confidence, 0.5)
        return True

    def _resolve_references(
        self, result: ContextResult, toks: list[str], snap: DesktopSnapshot
    ) -> None:
        refs: list[Reference] = []
        out: list[str] = []
        index = 0
        while index < len(toks):
            pair = tuple(toks[index : index + 2])
            token = toks[index]
            if pair == ("the", "other"):
                width = 2
                kind: str = "window"
                if index + 2 < len(toks) and toks[index + 2] in {"monitor", "screen"}:
                    kind, width = "monitor", 3
                elif index + 2 < len(toks) and toks[index + 2] in {"one", "window", "tab"}:
                    kind = "tab" if toks[index + 2] == "tab" else "window"
                    width = 3
                exclude = snap.focused_window_id if kind == "window" else None
                if exclude is None:
                    last = self._registry.last(kind)  # type: ignore[arg-type]
                    exclude = last.id if last else None
                entity = self._registry.other(kind, exclude)  # type: ignore[arg-type]
                mention = " ".join(toks[index : index + width])
                refs.append(self._ref(mention, kind, entity))
                out.append(self._mention_text(kind, entity) if entity else mention)
                index += width
                continue
            if (
                token in _ORDINALS
                and index + 1 < len(toks)
                and toks[index + 1]
                in {
                    "one",
                    "window",
                    "monitor",
                    "screen",
                    "result",
                }
            ):
                noun = toks[index + 1]
                kind = {"monitor": "monitor", "screen": "monitor", "result": "result_item"}.get(
                    noun, "window"
                )
                if noun == "one":
                    kind = self._ordinal_kind(_ORDINALS[token])
                entity = self._registry.ordinal(kind, _ORDINALS[token])  # type: ignore[arg-type]
                mention = f"{token} {noun}"
                refs.append(self._ref(mention, kind, entity))
                out.append(self._mention_text(kind, entity) if entity else mention)
                index += 2
                continue
            if pair == ("this", "window") or token in {"it", "this", "that"}:
                width = 2 if pair == ("this", "window") else 1
                entity = None
                if snap.focused_window_id:
                    entity = self._registry.get(snap.focused_window_id)
                if entity is None:
                    entity = self._registry.last("window")
                mention = " ".join(toks[index : index + width])
                refs.append(self._ref(mention, "window", entity))
                out.append(self._mention_text("window", entity) if entity else mention)
                index += width
                continue
            out.append(token)
            index += 1
        if refs:
            result.references = tuple(refs)
            result.standalone_command = " ".join(out)
            unresolved = [ref for ref in refs if ref.resolved_id is None]
            if unresolved:
                result.confidence = max(0.05, result.confidence - 0.25 * len(unresolved))
            if result.turn_kind is TurnKind.NEW_COMMAND:
                result.turn_kind = TurnKind.REFINEMENT

    def _ordinal_kind(self, position: int) -> str:
        for kind in ("result_item", "window", "monitor"):
            if len(self._registry.by_kind(kind)) >= position:
                return kind
        return "result_item"

    def _ref(self, mention: str, kind: str, entity: Any) -> Reference:
        candidates = tuple(e.label for e in self._registry.by_kind(kind))  # type: ignore[arg-type]
        return Reference(mention, kind, entity.id if entity else None, candidates)

    @staticmethod
    def _mention_text(kind: str, entity: Any) -> str:
        noun = {"window": "window", "monitor": "monitor", "tab": "tab"}.get(kind, "item")
        return f"the {noun} '{entity.label}'"

    def _redo(self, result: ContextResult, toks: list[str]) -> bool:
        if "again" not in toks:
            return False
        action = self._registry.last("action")
        if action is None:
            result.references += (Reference("again", "action", None, ()),)
            result.confidence = max(0.05, result.confidence - 0.25)
            return False
        tail = toks[toks.index("again") + 1 :]
        standalone = action.label + (" " + " ".join(tail) if tail else "")
        refs = list(result.references)
        refs.append(Reference("that again", "action", action.id, (action.label,)))
        # "…on the left monitor": bind the monitor entity if unambiguous.
        for side in ("left", "right"):
            if side in tail:
                monitors = [e for e in self._registry.by_kind("monitor") if side in words(e.label)]
                if len(monitors) == 1:
                    refs.append(
                        Reference(
                            f"the {side} monitor",
                            "monitor",
                            monitors[0].id,
                            tuple(e.label for e in self._registry.by_kind("monitor")),
                        )
                    )
                    standalone = standalone.replace(
                        f"the {side} monitor", f"the monitor '{monitors[0].label}'"
                    )
        result.references = tuple(refs)
        result.standalone_command = standalone
        result.turn_kind = TurnKind.REFINEMENT
        return True

    # -- remaining classification ---------------------------------------------

    def _classify_rest(self, result: ContextResult, toks: list[str], raw: str) -> None:
        joined = " ".join(toks)
        if "screen" in toks and {"error", "dialog", "popup", "this"} & set(toks):
            result.needs_screen_context = True
        if result.turn_kind is not TurnKind.NEW_COMMAND:
            return
        if is_dangling(result.standalone_command):
            result.turn_kind = TurnKind.INCOMPLETE
        elif ("go" in toks and "back" in toks) or "back to" in joined or "wapas" in toks:
            result.turn_kind = TurnKind.RETURN_TO_EARLIER
        elif raw.rstrip().endswith("?") or (toks and toks[0] in _QUESTION_STARTS):
            result.turn_kind = TurnKind.QUESTION
        elif len(toks) <= 4 and {token for token in toks} <= _CHITCHAT | {"you", "vox"}:
            result.turn_kind = TurnKind.CHITCHAT


# -- small-model path ---------------------------------------------------------

ContextualiserLLM = Callable[[dict[str, Any]], dict[str, Any]]


def load_contextualiser_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


class Contextualiser:
    """Code first; the small model only when the code path cannot resolve."""

    def __init__(self, code: CodeContextualiser, llm: ContextualiserLLM | None = None) -> None:
        self._code = code
        self._llm = llm
        self._prompt = load_contextualiser_prompt()

    def contextualise(
        self,
        utterance: str,
        *,
        snapshot: DesktopSnapshot | None = None,
        pending: PendingClarification | None = None,
        last_command: str | None = None,
        recent_turns: tuple[str, ...] = (),
    ) -> ContextResult:
        result = self._code.contextualise(
            utterance, snapshot=snapshot, pending=pending, last_command=last_command
        )
        if self._llm is None or not result.needs_llm():
            return result
        try:
            payload = {
                "system": self._prompt,
                "prompt_version": PROMPT_VERSION,
                "utterance": utterance,
                "recent_turns": list(recent_turns),
                "code_standalone": result.standalone_command,
                "language": result.language,
            }
            parsed = self._parse(self._llm(payload), fallback=result)
        except Exception:  # noqa: BLE001 - a bad model path must never break the turn
            return result
        return parsed

    def _parse(self, raw: dict[str, Any], *, fallback: ContextResult) -> ContextResult:
        if not isinstance(raw, dict):
            return fallback
        registry = self._code._registry  # ids are trusted only if they exist
        references: list[Reference] = []
        raw_refs = raw.get("references")
        if isinstance(raw_refs, list):
            for item in raw_refs:
                if not isinstance(item, dict):
                    continue
                resolved = item.get("resolved_id")
                if not (isinstance(resolved, str) and registry.get(resolved) is not None):
                    resolved = None
                candidates = item.get("candidates")
                references.append(
                    Reference(
                        mention=str(item.get("mention", "")),
                        kind=str(item.get("kind", "other")),
                        resolved_id=resolved,
                        candidates=tuple(candidates) if isinstance(candidates, list) else (),
                    )
                )
        try:
            kind = TurnKind(str(raw.get("turn_kind", fallback.turn_kind)))
        except ValueError:
            kind = fallback.turn_kind
        standalone = raw.get("standalone_command")
        result = ContextResult(
            addressed_to_assistant=bool(raw.get("addressed_to_assistant", True)),
            turn_kind=kind,
            standalone_command=standalone
            if isinstance(standalone, str) and standalone
            else fallback.standalone_command,
            references=tuple(references) or fallback.references,
            task_ref=raw.get("task_ref") if isinstance(raw.get("task_ref"), str) else None,
            needs_clarification=bool(raw.get("needs_clarification", False)),
            clarification_hint=raw.get("clarification_hint")
            if isinstance(raw.get("clarification_hint"), str)
            else None,
            needs_screen_context=bool(raw.get("needs_screen_context", False)),
            language=str(raw.get("language", fallback.language)),
            reply_language=fallback.reply_language,
            asr_repairs=fallback.asr_repairs,
            confidence=float(raw["confidence"])
            if isinstance(raw.get("confidence"), (int, float))
            else fallback.confidence,
            route="llm",
        )
        return result
