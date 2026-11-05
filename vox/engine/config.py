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


class WakeSensitivity(StrEnum):
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"


# sensitivity -> (stage-0 RMS gate, minimum stage-2 word confidence)
SENSITIVITY_PRESETS: dict[WakeSensitivity, tuple[float, float]] = {
    WakeSensitivity.LOW: (0.05, 0.85),
    WakeSensitivity.BALANCED: (0.03, 0.7),
    WakeSensitivity.HIGH: (0.015, 0.5),
}


@dataclass(frozen=True)
class WakeSettings:
    """Hands-free "Hi Vox" configuration (spec 4.0a). Settings model only;
    the Settings/QML surface lands with the LE4 UI states (LE1b decision)."""

    enabled: bool = False
    name: str = "Vox"
    greetings: tuple[str, ...] = ("hi", "hey")
    sensitivity: WakeSensitivity = WakeSensitivity.BALANCED
    chime: bool = True
    listen_timeout_s: float = 6.0
    calibration_offset: float = 0.0  # added to the RMS gate, from Calibrate

    @property
    def canonical(self) -> str:
        return self.name.strip().lower() or "vox"

    @property
    def uses_custom_name(self) -> bool:
        return self.canonical != "vox"

    @property
    def gate_rms(self) -> float:
        base, _ = SENSITIVITY_PRESETS[self.sensitivity]
        return max(0.005, base + self.calibration_offset)

    @property
    def min_confidence(self) -> float:
        return SENSITIVITY_PRESETS[self.sensitivity][1]

    def phrase_sets(self) -> dict[str, frozenset[str] | str]:
        """Token sets for contains_wake_phrase/strip_wake_tokens."""
        from vox.engine.i18n import WAKE_GREETINGS, WAKE_NAME_VARIANTS

        strong: set[str] = set()
        weak: set[str] = set()
        for table in WAKE_GREETINGS.values():
            strong.update(table["strong"])
            weak.update(table["weak"])
        strong.intersection_update({*self.greetings, "hai", "हाय", "हे"})
        variants = WAKE_NAME_VARIANTS.get(self.canonical, (self.canonical,))
        return {
            "strong": frozenset(strong),
            "weak": frozenset(weak),
            "names": frozenset(variants),
            "merged": frozenset(f"{greeting}{self.canonical}" for greeting in self.greetings),
            "canonical": self.canonical,
        }


def load_settings(environ: Mapping[str, str] | None = None) -> EngineSettings:
    env = os.environ if environ is None else environ
    raw = env.get("VOX_ENGINE_MODE", "legacy").strip().lower()
    try:
        mode = EngineMode(raw)
    except ValueError:
        mode = EngineMode.LEGACY  # unknown value: most conservative option
    return EngineSettings(mode=mode)
