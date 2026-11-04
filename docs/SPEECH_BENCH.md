# SPEECH BENCH — wake phrase & voice numbers

Rule (spec §0.3/§7): only measured numbers live here. Anything not yet
measured says so, with the reason and where it will be measured.

## Wake engine (L-10)

- **Stage 0/1:** RMS/VAD gate (`WakeSettings.gate_rms` per sensitivity) +
  phrase match on Vosk *partial* snippets (`vox/engine/wake.TwoStageWake`).
- **Stage 2:** Vosk *final* snippet must still match and clear the
  sensitivity's mean word-confidence bar (Low 0.85 / Balanced 0.70 /
  High 0.50). Clear alias matches ("hi box" @ high confidence) are
  accepted by design; marginal ones are rejected.
- **Engine/model:** Vosk 0.3.45 `KaldiRecognizer` (SetWords on),
  `vosk-model-small-en-us-0.15` (~40 MB). Toolkit and model are Apache-2.0
  (see `installer/licenses/THIRD_PARTY.md`). openWakeWord rejected: no
  trained "Hi Vox" model exists; Porcupine rejected: proprietary key.
- **Phrases:** greetings {hi, hey} (+ spellings hai/हाय/हे) × name "Vox",
  from `WakeSettings` + `vox/engine/i18n.py` — never hard-coded. "folks"
  is deliberately not a name variant (stock media greeting).

## Measured (sandbox, text/decision level — `scripts/wake_bench.py`, 2026-11-05)

Corpus: 14 scripted (transcript, confidence) cases → `TwoStageWake`.
Artifact: `artifacts/live_engine/wake_bench.json`.

| Sensitivity | False accepts | False rejects |
|---|---|---|
| Low | 0/9 | 0/5 |
| Balanced | 0/9 | 0/5 |
| High | 0/9 | 0/5 |

- Quiet-room gate skip: **100%** of silent frames never reach the decoder.
- Matcher+gate cost: **0.28 ms/frame** (≈0.1% of one core at 4 fps),
  *excluding Vosk inference*.
- Wake-to-feedback / stage-2 reject / timeout: proven in **virtual time**
  by `tests/live_engine/test_wake.py` (detect same tick ≤150 ms budget;
  reject ≤400 ms scenario; silent 6 s wake timeout). Wall-clock numbers
  are not claimed.

## Not measured yet (Windows run required)

| Metric | Gate (spec §7) | How |
|---|---|---|
| Audio false-accepts/hour (TV/podcast/noise) | ≤1 per 10 h | `python scripts/wake_bench.py --corpus <dir of *.neg.wav>` on Windows (model bundled by installer) |
| Audio false-reject: quiet / noisy / 2 m | ≤10% / ≤20% | same, `*.pos.wav` (record real voices: IN/US/UK English, Hindi-accented) |
| Idle CPU/RAM incl. Vosk inference | ≤3% core, ≤50 MB | Task Manager / `vox bench --wake` soak on Tier B hardware |
| Wake-to-feedback wall clock | ≤150 ms stage-1, ≤300 ms earcon | debug panel waterfall (LE6) |
| Premature-cut rate, field WER ±hotwords (EN/HI/Hinglish) | ≤3% cuts | voice harness, LE7. *Synthetic* repair-table WER measured at LE2: 0.562 → 0.000 (`scripts/context_bench.py`, docs/MODEL_BENCH.md) — not field WER. Groq `transcribe_detailed` (verbose_json confidence + glossary hotword prompt) implemented at LE2, awaiting live use. |
| Barge-in cancel latency (real winsound) | ≤150 ms | Windows bench; player polls cancel every 20 ms by design |

The sandbox cannot produce these: `alphacephei.com` (model host) is
unreachable and there is no microphone or Windows desktop (BLOCKERS #13).
First physical data point so far: one user report that "Hi Vox" did not
wake the legacy single-stage build (2026-11-05) — the two-stage engine +
"Heard locally" diagnostics exist to turn that into measurable cases.
