"""Pre-synthesised acknowledgements and earcons (spec §2/4.0c).

Ack *phrases* are chosen deterministically per language so feedback never
waits on an LLM/TTS round trip; earcons are generated in code (short sine
blips) — no audio assets to ship or license.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from typing import Literal

ACK_PHRASES: dict[str, dict[str, str]] = {
    "en": {"working": "Working on it.", "heard": "Okay.", "one_moment": "One moment."},
    "hi": {"working": "कर रहा हूँ।", "heard": "ठीक है।", "one_moment": "एक पल।"},
}

EarconKind = Literal["wake", "done", "error"]
_TONES: dict[str, tuple[int, int]] = {  # (frequency Hz, duration ms)
    "wake": (880, 90),
    "done": (660, 90),
    "error": (220, 160),
}


def ack_phrase(kind: str, language: str) -> str:
    table = ACK_PHRASES.get(language, ACK_PHRASES["en"])
    return table.get(kind, ACK_PHRASES["en"].get(kind, "Okay."))


def should_ack(*, tools_planned: int, already_spoken: bool, ack_already_played: bool) -> bool:
    """A canned ack is due when work will take a while and nothing was said."""
    return tools_planned >= 1 and not already_spoken and not ack_already_played


def earcon_wav(kind: EarconKind, *, sample_rate: int = 16000) -> bytes:
    frequency, duration_ms = _TONES[kind]
    frames = int(sample_rate * duration_ms / 1000)
    pcm = b"".join(
        struct.pack(
            "<h",
            int(9000 * math.sin(2 * math.pi * frequency * i / sample_rate)),
        )
        for i in range(frames)
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
