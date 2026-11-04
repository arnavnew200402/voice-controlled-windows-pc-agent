"""Glossary: ASR repair vocabulary (spec 4.3) — apps, aliases, wake names.

Repair is token-window phrase replacement against known variants, plus a
conservative phonetic-ish fallback for single tokens ("crow" -> Chrome).
Learned entries are *proposals* until confirmed (L-08): a user correction
("no, I said Notepad++") never silently rewrites the glossary.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"[^\W_]+(?:\+\+)?", re.UNICODE)  # keeps "Notepad++" as one token


def words(text: str) -> list[str]:
    return [match.group(0) for match in _WORD_RE.finditer(text.lower())]


@dataclass(frozen=True)
class Repair:
    heard: str
    fixed: str
    source: str = "glossary"


@dataclass(frozen=True)
class GlossaryEntry:
    canonical: str
    variants: tuple[str, ...] = ()
    source: str = "builtin"


@dataclass
class _Proposal:
    heard: str
    meant: str


# Canonical spoken names + the ways ASR commonly mangles them. App entries
# mirror the closed registry (groq_tools.AppArgs) plus common third-party
# apps the acceptance corpus references.
BUILTIN_ENTRIES: tuple[GlossaryEntry, ...] = (
    GlossaryEntry("Notepad", ("no pad", "note pad", "notpad")),
    GlossaryEntry("Notepad++", ("notepad plus plus", "note pad plus plus")),
    GlossaryEntry("Calculator", ("calculater",)),
    GlossaryEntry("Paint", ()),
    GlossaryEntry("Browser", ()),
    GlossaryEntry("Email", ("e mail",)),
    GlossaryEntry("Settings", ()),
    GlossaryEntry("FileExplorer", ("file explorer", "explorer", "files explorer")),
    GlossaryEntry("Calendar", ("calender",)),
    GlossaryEntry("Photos", ("photo",)),
    GlossaryEntry("MediaPlayer", ("media player", "windows media player")),
    GlossaryEntry("Chrome", ("crow", "crome", "google chrome")),
    GlossaryEntry("Edge", ("microsoft edge",)),
    GlossaryEntry("Word", ("microsoft word", "ms word")),
    GlossaryEntry("WordPad", ("word pad",)),
    GlossaryEntry("Visual Studio Code", ("vs code", "vscode", "visual studio")),
    GlossaryEntry("Vox", ("box", "fox", "walks")),
)


def _phonetic(word: str) -> str:
    """Crude sound key: first letter, drop later vowels/h/w, squash doubles."""
    cleaned = [c for c in word.lower() if c.isalpha()]
    if not cleaned:
        return ""
    head, tail = cleaned[0], [c for c in cleaned[1:] if c not in "aeiouhw"]
    squashed = "".join(c for i, c in enumerate(tail) if i == 0 or c != tail[i - 1])
    return head + squashed


class Glossary:
    def __init__(self, entries: tuple[GlossaryEntry, ...] = BUILTIN_ENTRIES) -> None:
        self._entries: list[GlossaryEntry] = list(entries)
        self._proposals: list[_Proposal] = []
        self._phrase_map: dict[tuple[str, ...], str] = {}
        self._rebuild()

    def _rebuild(self) -> None:
        self._phrase_map = {}
        for entry in self._entries:
            for phrase in (entry.canonical, *entry.variants):
                key = tuple(words(phrase))
                if key:
                    self._phrase_map[key] = entry.canonical

    @property
    def entries(self) -> list[GlossaryEntry]:
        return list(self._entries)

    def canonicals(self) -> list[str]:
        return [entry.canonical for entry in self._entries]

    def hotwords(self, extra: tuple[str, ...] = ()) -> str:
        """Whisper prompt seed (kept short: the API prompt budget is small)."""
        terms = [*extra, *self.canonicals()]
        return ", ".join(dict.fromkeys(terms))[:800]

    def ambiguous_matches(self, phrase: str) -> list[str]:
        """Canonicals a heard phrase could mean (>=2 => ask, edge case 17)."""
        heard_words = words(phrase)
        heard = " ".join(heard_words)
        if not heard:
            return []
        matches: set[str] = set()
        for entry in self._entries:
            canon_words = words(entry.canonical)
            canon = " ".join(canon_words)
            if canon == heard or heard in {" ".join(words(v)) for v in entry.variants}:
                matches.add(entry.canonical)
            elif len(canon_words) == 1 and len(heard_words) == 1 and canon.startswith(heard):
                matches.add(entry.canonical)  # "word" also fits WordPad
        return sorted(matches)

    def repair(self, text: str) -> tuple[str, list[Repair]]:
        tokens = words(text)
        if not tokens:
            return text, []
        out: list[str] = []
        repairs: list[Repair] = []
        index = 0
        while index < len(tokens):
            matched: tuple[int, str] | None = None
            for width in (3, 2, 1):
                window = tuple(tokens[index : index + width])
                if width <= len(tokens) - index and window in self._phrase_map:
                    matched = (width, self._phrase_map[window])
                    break
            if matched is not None:
                width, canonical = matched
                heard = " ".join(tokens[index : index + width])
                if heard != canonical.lower():
                    repairs.append(Repair(heard=heard, fixed=canonical))
                out.append(canonical)
                index += width
                continue
            token = tokens[index]
            fixed = self._phonetic_fix(token)
            if fixed is not None:
                repairs.append(Repair(heard=token, fixed=fixed, source="phonetic"))
                out.append(fixed)
            else:
                out.append(token)
            index += 1
        return " ".join(out), repairs

    def _phonetic_fix(self, token: str) -> str | None:
        if len(token) < 4:
            return None
        key = _phonetic(token)
        best: tuple[float, str] | None = None
        for entry in self._entries:
            for candidate_word in words(entry.canonical):
                if _phonetic(candidate_word) == key and candidate_word != token:
                    ratio = difflib.SequenceMatcher(None, token, candidate_word).ratio()
                    if ratio >= 0.6 and (best is None or ratio > best[0]):
                        best = (ratio, entry.canonical)
        return best[1] if best else None

    # -- learned entries (proposals until confirmed, L-08) -----------------

    def propose(self, heard: str, meant: str) -> None:
        proposal = _Proposal(heard=" ".join(words(heard)), meant=meant)
        if proposal.heard and proposal not in self._proposals:
            self._proposals.append(proposal)

    def proposals(self) -> list[tuple[str, str]]:
        return [(p.heard, p.meant) for p in self._proposals]

    def confirm(self, heard: str) -> bool:
        key = " ".join(words(heard))
        for proposal in list(self._proposals):
            if proposal.heard == key:
                self._proposals.remove(proposal)
                self._entries.append(
                    GlossaryEntry(proposal.meant, (proposal.heard,), source="user_correction")
                )
                self._rebuild()
                return True
        return False


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level Levenshtein distance / reference words (bench helper)."""
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if ref_word == hyp_word else 1),
                )
            )
        previous = current
    return previous[-1] / len(ref)
