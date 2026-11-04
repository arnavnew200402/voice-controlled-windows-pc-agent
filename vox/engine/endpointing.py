"""Adaptive endpointing and the pre-roll ring buffer (spec 4.2a).

Three levels: soft end (short silence + complete-looking partial) lets the
pipeline speculate with the read-only whitelist; hard end commits to
processing; resumed speech after a soft end discards the speculation.
"Complete-looking" is a turn-taking heuristic over trailing tokens
(EN + HI), not intent classification (L-01/L-02).
"""

from __future__ import annotations

import math
import unicodedata
from collections import deque
from enum import StrEnum

from vox.engine.clock import Clock, SystemClock
from vox.engine.config import EngineSettings

DANGLING_TOKENS = {
    # English conjunctions/prepositions/determiners/fillers.
    "and",
    "then",
    "to",
    "the",
    "a",
    "an",
    "of",
    "for",
    "on",
    "in",
    "so",
    "but",
    "or",
    "with",
    "my",
    "this",
    "that",
    "um",
    "uh",
    # Hindi/Hinglish equivalents (Roman script).
    "aur",
    "phir",
    "ko",
    "mein",
    "ka",
    "ki",
    "ke",
    "toh",
    "se",
}


def tokens(text: str) -> list[str]:
    return "".join(
        char.lower() if char.isalnum() or unicodedata.category(char).startswith("M") else " "
        for char in text
    ).split()


def is_dangling(text: str) -> bool:
    parts = tokens(text)
    if not parts:
        return True
    return parts[-1] in DANGLING_TOKENS


class Decision(StrEnum):
    NONE = "none"
    SOFT_END = "soft_end"
    HARD_END = "hard_end"


class Endpointer:
    """Silence/partial-driven end-of-turn state machine (single utterance)."""

    def __init__(self, settings: EngineSettings | None = None) -> None:
        self._settings = settings or EngineSettings()
        self._partial = ""
        self._last_speech = 0.0
        self._last_change = 0.0
        self._soft_ended = False
        self._resumed = False
        self._done = False

    def reset(self, now: float) -> None:
        self._partial = ""
        self._last_speech = now
        self._last_change = now
        self._soft_ended = False
        self._resumed = False
        self._done = False

    @property
    def partial(self) -> str:
        return self._partial

    @property
    def soft_ended(self) -> bool:
        return self._soft_ended

    def consume_resumed(self) -> bool:
        resumed, self._resumed = self._resumed, False
        return resumed

    def _note_activity(self, now: float) -> None:
        self._last_speech = now
        if self._soft_ended and not self._done:
            self._soft_ended = False
            self._resumed = True

    def on_speech(self, rms: float, now: float) -> None:
        if rms >= self._settings.speech_rms:
            self._note_activity(now)

    def on_partial(self, text: str, now: float) -> None:
        cleaned = " ".join(text.split())
        if cleaned != self._partial:
            self._partial = cleaned
            self._last_change = now
        if cleaned:
            self._note_activity(now)

    def poll(self, now: float) -> Decision:
        if self._done or not self._partial:
            return Decision.NONE
        silence = now - self._last_speech
        dangling = is_dangling(self._partial)
        hard_after = (
            self._settings.hard_silence_dangling_s
            if dangling
            else self._settings.hard_silence_complete_s
        )
        if silence >= hard_after:
            self._done = True
            self._soft_ended = False
            return Decision.HARD_END
        if (
            not self._soft_ended
            and not dangling
            and silence >= self._settings.soft_silence_s
            and now - self._last_change >= self._settings.soft_silence_s
        ):
            self._soft_ended = True
            return Decision.SOFT_END
        return Decision.NONE


class PreRollBuffer:
    """Last ~1.5 s of microphone frames, in RAM only.

    Keeps "Hi Vox, open Chrome" in one breath intact: when the wake phrase
    is verified, the command audio starts from the phrase boundary instead
    of from whenever verification finished.
    """

    def __init__(
        self,
        clock: Clock | None = None,
        seconds: float = 1.5,
        frame_seconds: float = 0.25,
    ) -> None:
        self._clock = clock or SystemClock()
        capacity = max(1, math.ceil(seconds / frame_seconds))
        self._frames: deque[tuple[float, bytes]] = deque(maxlen=capacity)

    def push(self, frame: bytes, at: float | None = None) -> None:
        self._frames.append((self._clock.monotonic() if at is None else at, frame))

    def audio_from(self, since: float) -> bytes:
        return b"".join(frame for stamp, frame in self._frames if stamp >= since)

    def clear(self) -> None:
        self._frames.clear()

    def __len__(self) -> int:
        return len(self._frames)
