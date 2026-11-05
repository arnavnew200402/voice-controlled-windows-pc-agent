# FINAL REPORT

## What was asked vs. what exists
The brief describes a Windows 10/11 Python/Qt agent with a local speech/LLM stack, Win32 integration and installers. **That product does not exist in this repository and its Windows integration cannot be verified here** (Linux sandbox, no display/root/Windows APIs). What was built instead is a runnable Next.js + Postgres application that implements, and tests, the parts of the spec that are platform-independent, and is structured so they port 1:1.

## Exists and verified (by running it)
| Area | Evidence |
|---|---|
| Safety engine (tiers, escalation, bound approvals, T2 click-only, redaction, audit) | **25/25** red-team cases pass on the production build (`artifacts/redteam.json`, ≈12 s). Includes a seeded path-smuggling fuzz: **466 variants, 0 bypasses**. |
| Offline guard | RT-21: in offline mode the demo commands succeed, 0 outbound attempts, guard blocks a direct cloud attempt. *Application-level only.* |
| Mid-task failover | RT-22: network cut after step 1 → remaining step replayed on local provider, both steps verified, ModeChanged emitted. |
| Stop latency | RT-23: stop → turn aborted in ≈1 ms (limit 150 ms) in-process. |
| Demo script (15.7) | Open Notepad + type, move window to right monitor, volume 30, screen inspection, search + open first result, folder + file on Desktop, delete-Downloads approval (sandbox only, 14 items → Recycle Bin), shutdown needs click (voice denied), format-disk blocked — all runnable from the UI against the virtual PC. |
| Build gates | `next typegen`, `tsc --noEmit`, `npm run build`, `build_and_start` (see final message). |

## Native work in progress (2026-11-04)

A standalone Python `vox` package now contains an in-memory approval primitive and a placeholder entry point. On Linux, 13 portable approval tests passed, and Ruff and mypy checks passed. It is not connected to the web reference or any Windows tool. A synthetic PySide6/QML notch design studio was subsequently added; it is not a functioning agent. Windows CI is configured but has not been observed running. The primitive does not prove input provenance, enforce path policy, log approvals, or cancel an action already consumed. See `ARCHITECTURE.md` for integration prerequisites.

## Exists but NOT verified
- The notch UI (SVG shape, springs, states, hover panel, echo, mode badge, privacy dots, reduce-motion). It type-checks, builds and serves (HTTP 200), but **no screenshot or frame-time was captured** — headless Chromium would not start in the sandbox (`docs/BLOCKERS.md`). Visual quality, spring feel and the claimed ≤16.6 ms p95 are unmeasured. Run `scripts/ui-capture.mjs` or open the Perf tab.
- Claude and Ollama adapters: written, never run against a live endpoint.
- Browser SpeechRecognition/speechSynthesis voice I/O: needs Chrome/Edge and mic permission; untested here.

## Not built
Functional Windows app (real event-driven PySide6/QML, verified Win32 flags, UIA, Core Audio), wake word / VAD / Faster-Whisper / Piper, AEC + loopback voice-injection defence, socket-level offline guard and firewall test, the general Windows tool suite, click_target/read_ui/drag/zip, CDP browser + Chrome extension, hardware probe, model benches (`MODEL_BENCH.md`, `SPEECH_BENCH.md` don't exist — nothing was measured), settings window, onboarding, i18n beyond EN/HI notch strings, installers/signing/`vox doctor`, 8-hour soak.

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

## UI-first prototype (2026-11-04)

A Qt Quick design studio and a separate click-through notch preview expose ten synthetic states. `artifacts/ui/native/` contains Qt offscreen screenshots and frame-swapped interval samples from Linux software rendering. 14 Python tests passed locally, including a Qt render smoke test; Windows CI was configured but not observed. No Windows hit-testing, focus, GPU frame-time or idle CPU measurements have been made. No Windows installer exists yet.

## Connected sandbox (2026-11-04)

The native studio now drives a background, in-memory simulation and displays typed state/tool/approval/reply events. Open and delete examples are fake; the approval store is used only for the virtual delete. Deny, timeout, stop, changed-snapshot and single-use paths have tests. On Linux, 22 Python tests, Ruff and mypy passed. This is not an integration of real speech, providers, Windows actions, production policy/audit or an installer. Windows execution and physical input remain unverified.

## Experimental local text path (2026-11-04)

A separate CLI can call an explicitly configured local Ollama model with a strict, one-tool schema and launch Windows Notepad or use `--dry-run`. Only fixed system Notepad is allowed; successful results require process/foreground verification. Linux tests use fakes and a recorded local loopback server; the actual Windows launcher and live Ollama model have not been run. 45 Python tests, Ruff, and mypy passed locally. This does not connect the UI or voice, implement general PC control, or provide an installer or a tested offline guarantee.

## ChatGPT OAuth provider (2026-11-04)

The experimental CLI now defaults to OpenAI's documented SIWC ChatGPT-plan OAuth flow and streamed Responses API, instead of Ollama. It verifies an RS256 ID token and required scopes, and stores the session using Windows DPAPI. The only executable tool remains Notepad. 66 tests passed on Linux and one Windows-only DPAPI test was skipped; tests used generated test keys, fake tokens and recorded responses. **No live OAuth, ChatGPT inference, DPAPI or Windows launch has been tested.** Sessions require manual re-sign-in after expiry; token refresh, logout/revocation, multiple accounts, UI/voice integration, broad tools and the installer remain incomplete.
