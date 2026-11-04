"""Live Command Engine settings.

The engine is opt-in until the LE7 A/B: ``mode`` defaults to ``legacy`` so
the shipped hands-free path is bit-identical unless ``VOX_ENGINE_MODE=live``
(or a future persisted setting) turns the live pipeline on.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class EngineMode(StrEnum):
    LEGACY = "legacy"
    LIVE = "live"


@dataclass(frozen=True)
class EngineSettings:
    mode: EngineMode = EngineMode.LEGACY
    # Endpointing (spec 4.2a). The dangling hard-end (1.2 s) deliberately
    # exceeds the master spec's 500-800 ms band; recorded in DECISIONS (LE1).
    soft_silence_s: float = 0.25
    hard_silence_complete_s: float = 0.5
    hard_silence_dangling_s: float = 1.2
    merge_window_s: float = 1.5
    preroll_s: float = 1.5
    followup_window_s: float = 6.0
    speech_rms: float = 0.03


def load_settings(environ: Mapping[str, str] | None = None) -> EngineSettings:
    env = os.environ if environ is None else environ
    raw = env.get("VOX_ENGINE_MODE", "legacy").strip().lower()
    try:
        mode = EngineMode(raw)
    except ValueError:
        mode = EngineMode.LEGACY  # unknown value: most conservative option
    return EngineSettings(mode=mode)
