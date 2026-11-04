# FINAL REPORT

## What was asked vs. what exists
The brief describes a Windows 10/11 Python/Qt agent with a local speech/LLM stack, Win32 integration and installers. **That product does not exist in this repository, and could not have been verified here** (Linux sandbox, no display/root/Windows APIs). What was built instead is a runnable Next.js + Postgres application that implements, and tests, the parts of the spec that are platform-independent, and is structured so they port 1:1.

## Exists and verified (by running it)
| Area | Evidence |
|---|---|
| Safety engine (tiers, escalation, bound approvals, T2 click-only, redaction, audit) | **25/25** red-team cases pass on the production build (`artifacts/redteam.json`, ≈12 s). Includes a seeded path-smuggling fuzz: **466 variants, 0 bypasses**. |
| Offline guard | RT-21: in offline mode the demo commands succeed, 0 outbound attempts, guard blocks a direct cloud attempt. *Application-level only.* |
| Mid-task failover | RT-22: network cut after step 1 → remaining step replayed on local provider, both steps verified, ModeChanged emitted. |
| Stop latency | RT-23: stop → turn aborted in ≈1 ms (limit 150 ms) in-process. |
| Demo script (15.7) | Open Notepad + type, move window to right monitor, volume 30, screen inspection, search + open first result, folder + file on Desktop, delete-Downloads approval (sandbox only, 14 items → Recycle Bin), shutdown needs click (voice denied), format-disk blocked — all runnable from the UI against the virtual PC. |
| Build gates | `next typegen`, `tsc --noEmit`, `npm run build`, `build_and_start` (see final message). |

## Exists but NOT verified
- The notch UI (SVG shape, springs, states, hover panel, echo, mode badge, privacy dots, reduce-motion). It type-checks, builds and serves (HTTP 200), but **no screenshot or frame-time was captured** — headless Chromium would not start in the sandbox (`docs/BLOCKERS.md`). Visual quality, spring feel and the claimed ≤16.6 ms p95 are unmeasured. Run `scripts/ui-capture.mjs` or open the Perf tab.
- Claude and Ollama adapters: written, never run against a live endpoint.
- Browser SpeechRecognition/speechSynthesis voice I/O: needs Chrome/Edge and mic permission; untested here.

## Not built
Windows app (PySide6/QML, Win32 flags, UIA, Core Audio), wake word / VAD / Faster-Whisper / Piper, AEC + loopback voice-injection defence, socket-level offline guard and firewall test, real Windows tools, click_target/read_ui/drag/zip, CDP browser + Chrome extension, hardware probe, model benches (`MODEL_BENCH.md`, `SPEECH_BENCH.md` don't exist — nothing was measured), settings window, onboarding, i18n beyond EN/HI notch strings, installers/signing/`vox doctor`, 8-hour soak.

## Numbers
- Upstream baselines: Aemyos guards file 86 tests → 1 failure + 36 errors (missing Windows/audio deps on Linux). Wyzer ≈366 tests → 31 failures on Linux (Windows-only backends).
- Own: 25/25 red-team; 466 fuzz variants / 0 bypasses; tool count ≈45 visible + 4 hidden T3.
- Not measured: wake→visual latency, STT/LLM/TTS latency, idle CPU/GPU, frame times, WER, wake-word FA/FR, memory growth.

## Honest weaknesses
- The LLM in tests/demo is a scripted fake (keyword matching). It proves the harness and safety layer, not natural-language understanding. No ≥80% model acceptance gate was run.
- "Physical confirmation" and "voice injection" defences are weaker in a browser than the spec requires (see `SAFETY.md`).
- Taint tracking is turn-wide (over-warns).

## How to run
`npm run build && npx next start`, open `/`. Try the demo list, "Run UI demo", Safety lab → Run suite. Optional env: `ANTHROPIC_API_KEY`, `OLLAMA_MODEL` (+`OLLAMA_URL`), `VOX_SIM_PROVIDERS=off`, `VOX_RECOVERY_MS`.
