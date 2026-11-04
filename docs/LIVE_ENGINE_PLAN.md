# Live Command Engine — LE0 audit & plan (2026-11-05, base commit `1af9145`)

Goal (spec §0.1): replace "final transcript → one memoryless LLM request" with a
session timeline, turn manager, layered memory, contextualiser, cache-friendly
streamed pipeline, background memory updates, and Siri-style "Hi Vox" wake —
without weakening the existing safety layer (single-use, argument-bound
approvals; click approval for CONFIRM tier). Everything ships behind
`engine.mode = legacy | live`, default **legacy** until LE7 A/B.

## 1. Where things live today

| Concern | Today | File(s) |
|---|---|---|
| Wake word | Vosk 0.3.45 `KaldiRecognizer`, model `vosk-model-small-en-us-0.15` (~40 MB, Apache-2.0; toolkit Apache-2.0 — see `installer/licenses/THIRD_PARTY.md`), unconstrained decode + phrase matcher. No numeric threshold (match on partial/final text). Phrases are hard-coded constants. | `vox/voice/wake.py` |
| VAD / endpointing | None for wake (every 250 ms frame decoded). Command capture: RMS energy gate, fixed threshold 0.03, fixed 1.1 s trailing silence, 6 s no-speech, 15 s cap. | `vox/voice/audio.py` (`record_until_silence`, `frame_rms`) |
| STT | Groq `whisper-large-v3-turbo`, multipart upload, `response_format=json` (text only — no confidence, no language pin, no prompt/hotwords). | `vox/agent/groq.py:121` |
| Orchestration | Hands-free state machine on a daemon thread (wake→capture→process→speak→wake; approval pauses spotting); results via `queue.Queue` polled by a 25 ms QTimer. | `vox/voice/handsfree.py`, `vox/voice/service.py`, `vox/ui/groq_model.py` |
| LLM request builder | One inline 171-char system literal + single user message + all 15 tool schemas, `stream:false`, exactly-one-tool-call enforced downstream. | `vox/agent/groq.py:88`, schemas in `vox/agent/groq_tools.py` |
| TTS | Groq `canopylabs/orpheus-v1-english` (voice `hannah`), whole-utterance WAV ≤200 chars; playback `winsound.PlaySound(SND_MEMORY)` — blocking, not interruptible, no spoken offset. | `vox/agent/groq.py:146`, `vox/voice/audio.py:136` |
| Event bus / timeline | None on the Groq path (queue tuples). Pydantic events exist but only the demo engine emits them. | `vox/events.py`, `vox/demo/` |
| Task engine | None: one action per turn, `_busy` serialisation in the UI model. | `vox/ui/groq_model.py` |
| Memory store (§10) | None. Only DPAPI-encrypted API-key files and the wake-model cache exist. No SQLite anywhere. | `vox/agent/auth_storage.py`, `vox/agent/groq_key.py`, `vox/voice/wake.py` |
| Approval flow | Single-use, argument-hash-bound `ApprovalStore`; tiers are two today: SAFE (no approval) / CONFIRM (click). Spec T0/T1/T2 maps SAFE→T0, CONFIRM→T1, T2 reserved (no T2 tools exist yet). | `vox/approvals.py`, `vox/agent/groq_tools.py` |
| Provider router | None: Groq HTTPS only (45 s timeout, no streaming/fallback). Dormant `ChatProvider` implementations (Codex, Ollama) + `run_turn` are unused by the app. | `vox/agent/groq.py`, `provider.py`, `chatgpt.py`, `ollama.py`, `turn.py` |

## 2. How the current turn is built (measured, `scripts/live_engine_baseline.py`)

`GroqClient.chat` sends exactly **2 messages** (system literal + the raw
transcript), all 15 tool schemas, `stream:false` — **prior turns are never
included; there is no memory of any kind** (payload: 7,763 bytes for
"open calculator"). The reply must contain exactly one tool call, which
`GroqRegistry.plan` validates (Pydantic args, tier from the closed registry,
fail-closed on anything else); CONFIRM actions wait for a click approval;
the tool's evidence string is then spoken via TTS. Compound commands,
corrections, and references ("close it") cannot work today.

## 3. Voice-layer weaknesses (fix phase / disposition)

1. Fixed 1.1 s silence timer, fixed RMS threshold → **LE1** (soft/hard adaptive endpointing).
2. Partials used only for wake matching; never for endpointing/speculation → **LE1/LE1b**.
3. No STT hotwords/prompt/language; `response_format=json` discards confidence → **LE2** (glossary prompt + `verbose_json` confidence).
4. TTS blocking & uncancellable, no spoken offset → **LE1** (async cancellable player + offset).
5. Barge-in: half-duplex only (mic closed during TTS + 0.4 s guard) → **LE1** documents/improves stop paths; true AEC full-duplex **logged, not fixing** in this program (no distributable AEC available; revisit as LE7 stretch).
6. No pre-roll: "Hi Vox open Chrome" in one breath loses the command → **LE1** ring buffer, **LE1b** cut/strip.
7. No ASR-confidence handling anywhere → **LE2** capture, **LE4** tiered gate.
8. Deterministic stop: UI Stop + cancel event exist; no spoken control plane (stop/mute/yes-no) → **LE1** (closed set per L-02; voice approval stays off until its LE tests exist — click remains supreme).
9. Blocking, unstreamed network calls (worker thread, sequential, 45 s timeouts) → **LE4** streaming/early dispatch, **LE6** per-turn fallback.
10. No per-stage timing → **LE1** `LatencySample`, **LE6** debug waterfall.
11. Wake phrases hard-coded, no config/i18n; baseline text corpus misses `hai vox`, `hi folks` → **LE1b**.
12. Single-stage wake (the spotter *is* an STT; no verifier/score) → **LE1b**: add VAD/RMS gate as stage-0/1 cheap pass + Vosk verify with word confidences; openWakeWord needs a trained custom model (no "Hi Vox" model exists), Porcupine needs a proprietary key — both rejected for now, revisit if a model is trained.
13. Wake-only timeout exists only implicitly (6 s no-speech capture abort) → **LE1b** explicit setting/state.
14. No lock-screen / mic-busy suspension (mic errors surface as error→off) → **LE1b** (WTS lock events + suspended state).
15. No loopback/AEC gating (TV could wake it; approvals still protect actions) → **LE1b** best-effort (evaluate WASAPI loopback capture options/licences; half-duplex guard remains).
16. Idle detector cost incl. Vosk inference unmeasured → **LE1b** Windows bench (sandbox cannot fetch the model — see §6).
17. Extra (found in audit): no timeline/ledger, evidence is a bare UI string, exactly-one-tool-call blocks compound commands → **LE1/LE4/LE5**.

## 4. Module map (new package, thin adapters — safety layer untouched)

New `vox/engine/`: `config.py` (mode flag, settings), `clock.py` (injectable
Clock), `timeline.py` (session timeline over extended `vox/events.py` — no
second ledger), `turns.py` (turn manager, commit point, generations),
`endpointing.py`, `control.py` (L-02 closed set, EN+HI), `context.py`
(contextualiser code path), `ledger.py` (actions ledger + entity registry,
deterministic writers), `memory.py` (SQLite session store, user card,
preferences), `retrieval.py` (device index), `pipeline.py` (per-turn
orchestration, streaming), `glossary.py`, `i18n.py`, `prompts/v2/*.md`
(inside the package so PyInstaller ships them as package data; spec's
`prompts/v2/` intent, adjusted for packaging — logged in DECISIONS).
Adapters wrap, never replace: `GroqRegistry`/`ApprovalStore` (tiers &
approval binding unchanged), `GroqClient` (+ streaming variant), wake engine,
audio iterators, TTS. UI: `groq_model.py` gains a live-mode branch; QML gets
states in LE4. Tests: `tests/live_engine/` (replay harness LE1), added to
the Windows CI matrix per phase. Bench: `scripts/live_engine_baseline.py`
(LE0), `vox bench --wake` in LE1b.

## 5. State storage decision

In-process session state, checkpointed every turn to **SQLite (WAL)** at
`%LOCALAPPDATA%\vox\session\session.db` (path helper mirrors
`wake.cached_model_path`; `~/.local/share/vox/session/` fallback for dev).
Justification: stdlib `sqlite3` (zero new dependencies, no licence risk),
crash-safe single-writer store for a single-process desktop app, spec
default. Transcripts are written only under the user's opt-in flag (L-03);
the audit trail keeps tool-level records only. Revisit only if a second
process ever needs concurrent writes.

## 6. Baseline (`artifacts/live_engine/baseline.json`, legacy path)

Measured in the Linux sandbox (fake backend/transport; no mic/key/network):
legacy 30-command replay ×3 — plan p50 **0.010 ms** / p95 **0.043 ms** (n=78),
approve+execute (fake) p50 **0.004 ms** / p95 **0.041 ms** (n=57, 57/57 ok;
folder/file plan items error on real-filesystem binding absent here —
fixture-covered in `tests/test_groq_voice.py`). LLM request: 2 messages, no
history, 7,763 B, 15 schemas, `stream:false`. Wake **text-matcher** corpus:
false-reject 2/20 (`hai vox`, `hi folks`), false-accept 0/20. Idle matcher
loop (RMS+match @4 fps, **excluding Vosk inference**): 0.094% of one core,
process RSS 32.1 MB. **Not measured** (recorded with reasons in the JSON):
audio wake FA/FR and Vosk idle CPU/RAM (model host unreachable from sandbox,
no microphone → Windows bench in LE1b), Groq STT/chat/TTS latencies (no API
key; stubbed per §0.3), real-desktop end-to-end (physical checklist).
Existing suite at `1af9145`: **161 passed, 1 skipped** (Linux offscreen,
2026-11-05); Windows CI green on the same commit (runs 41892253617 /
41892253599).
