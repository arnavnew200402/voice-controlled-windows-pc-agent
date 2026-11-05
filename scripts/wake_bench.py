"""Wake-phrase bench (`vox bench --wake` equivalent) for LE1b.

Two levels, honestly labelled:

1. Always available: the *text-matcher + two-stage decision* level — a
   scripted corpus of (transcript, final confidence) pairs run through
   ``TwoStageWake`` per sensitivity, plus gate skip-rate and per-frame
   matcher cost. This measures our matcher/policy, not acoustics.
2. `--corpus DIR`: audio level — labelled WAV files (`*.pos.wav` /
   `*.neg.wav`, 16 kHz mono int16) decoded by the real Vosk engine.
   Requires the wake model, which this sandbox cannot download; run it on
   Windows where the installer bundles the model. Without a model it
   records `not_measured` instead of inventing numbers.

Output: artifacts/live_engine/wake_bench.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vox.engine.clock import VirtualClock
from vox.engine.config import WakeSensitivity, WakeSettings
from vox.engine.wake import TwoStageWake
from vox.voice.audio import frame_rms
from vox.voice.wake import ScoredSnippet, find_model

# (heard text, final word confidence, should_wake) — confidences model a
# clearly-spoken phrase (~0.9) vs. a marginal/TV-distance one (~0.4).
TEXT_CORPUS: list[tuple[str, float, bool]] = [
    ("hi vox", 0.95, True),
    ("hey vox", 0.92, True),
    ("hai vox", 0.9, True),
    ("hi vox open chrome", 0.9, True),
    ("hi box", 0.9, True),  # clear alias: accepted by design
    ("hi box", 0.4, False),  # marginal alias: stage-2 must reject
    ("hi vox", 0.35, False),  # marginal exact phrase: rejected at Balanced
    ("high fox", 0.95, False),
    ("hi folks", 0.95, False),
    ("a box of chocolates", 0.95, False),
    ("i walks every day", 0.95, False),
    ("okay vox", 0.95, False),  # not a configured greeting by default
    ("say hi to the fox", 0.9, False),
    ("the weather is nice", 0.95, False),
]

LOUD = (8000).to_bytes(2, "little", signed=True) * 4000
QUIET = (50).to_bytes(2, "little", signed=True) * 4000


class _ScriptedEngine:
    def __init__(self, snippet: ScoredSnippet) -> None:
        self._snippet = snippet

    def feed_scored(self, frame: bytes) -> ScoredSnippet:
        return self._snippet

    def reset(self) -> None:
        pass


def text_level(sensitivity: WakeSensitivity) -> dict[str, Any]:
    settings = WakeSettings(enabled=True, sensitivity=sensitivity)
    false_accepts: list[str] = []
    false_rejects: list[str] = []
    for text, conf, should_wake in TEXT_CORPUS:
        spotter = TwoStageWake(
            _ScriptedEngine(ScoredSnippet(text=text, final=True, confidence=conf)),
            settings,
            VirtualClock(),
        )
        woke = any(step.kind == "verified" for step in spotter.feed(LOUD, frame_rms(LOUD)))
        if woke and not should_wake:
            false_accepts.append(f"{text}@{conf}")
        if should_wake and not woke:
            false_rejects.append(f"{text}@{conf}")
    positives = sum(1 for _t, _c, want in TEXT_CORPUS if want)
    negatives = len(TEXT_CORPUS) - positives
    return {
        "corpus": len(TEXT_CORPUS),
        "false_accepts": false_accepts,
        "false_accept_rate": round(len(false_accepts) / negatives, 3) if negatives else 0.0,
        "false_rejects": false_rejects,
        "false_reject_rate": round(len(false_rejects) / positives, 3) if positives else 0.0,
    }


def gate_and_cost() -> dict[str, Any]:
    settings = WakeSettings(enabled=True)
    spotter = TwoStageWake(
        _ScriptedEngine(ScoredSnippet(text="", final=True, confidence=None)),
        settings,
        VirtualClock(),
    )
    for _ in range(240):  # 60 s of quiet room at 4 fps
        spotter.feed(QUIET, frame_rms(QUIET))
    start = time.perf_counter()
    frames = 4000
    for _ in range(frames):
        frame_rms(LOUD)
        spotter.feed(QUIET, frame_rms(QUIET))
    per_frame_ms = (time.perf_counter() - start) * 1000 / frames
    return {
        "quiet_frames_skipped_pct": round(100 * spotter.gate_skipped / spotter.frames_seen, 1),
        "matcher_plus_gate_ms_per_frame": round(per_frame_ms, 4),
        "note": "Excludes Vosk inference (model unavailable in sandbox).",
    }


def audio_level(corpus_dir: Path | None) -> dict[str, Any]:
    if corpus_dir is None:
        return {"status": "not_measured", "reason": "no --corpus directory given"}
    model = find_model()
    if model is None:
        return {
            "status": "not_measured",
            "reason": "wake model not found (alphacephei.com unreachable from sandbox); "
            "run on Windows with the installer bundle",
        }
    from vox.voice.wake import VoskWakeEngine

    settings = WakeSettings(enabled=True)
    results: dict[str, Any] = {"model": str(model), "files": {}}
    false_accepts = false_rejects = positives = negatives = 0
    for wav_path in sorted(corpus_dir.glob("*.wav")):
        want = wav_path.name.endswith(".pos.wav")
        with wave.open(str(wav_path), "rb") as wav:
            pcm = wav.readframes(wav.getnframes())
        spotter = TwoStageWake(VoskWakeEngine(), settings, VirtualClock())
        woke = False
        frame_bytes = 8000
        for offset in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
            chunk = pcm[offset : offset + frame_bytes]
            if any(s.kind == "verified" for s in spotter.feed(chunk, frame_rms(chunk))):
                woke = True
                break
        results["files"][wav_path.name] = {"expected": want, "woke": woke}
        positives += 1 if want else 0
        negatives += 0 if want else 1
        false_accepts += 1 if woke and not want else 0
        false_rejects += 1 if want and not woke else 0
    results.update(
        {
            "status": "measured",
            "false_accept_rate": round(false_accepts / negatives, 3) if negatives else 0.0,
            "false_reject_rate": round(false_rejects / positives, 3) if positives else 0.0,
        }
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Wake-phrase bench")
    parser.add_argument("--corpus", type=Path, default=None)
    args = parser.parse_args()
    report: dict[str, Any] = {
        "phase": "LE1b",
        "environment": "Linux sandbox (text level) — audio level needs Windows + bundled model",
        "text_level_by_sensitivity": {
            sensitivity.value: text_level(sensitivity) for sensitivity in WakeSensitivity
        },
        "gate_and_cost": gate_and_cost(),
        "audio_level": audio_level(args.corpus),
    }
    output = Path("artifacts/live_engine/wake_bench.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
