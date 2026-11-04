# BACKLOG

## Done
- [x] M0-01 Clone + read both repos, run upstream tests, `AUDIT.md`
- [x] M0-02 Architecture + decisions docs
- [x] M5-01 Tier model + argument-level escalation (`policy.ts`)
- [x] M5-02 Bound approvals, expiry, single-use, T2 click-only (`approvals.ts`)
- [x] M5-03 Untrusted tagging, markup strip, secret redaction (`redact.ts`)
- [x] M5-04 Audit log (Postgres, redacted)
- [x] M5-05 Red-team suite, 25 cases, seeded path fuzzer (466 variants)
- [x] M3-01 Provider router, hysteresis, mid-task failover
- [x] M3-02 Offline guard (app-level) + test
- [x] M4-01 Tool registry + ~45 tools + evidence read-back (virtual PC)
- [x] M4-02 Task engine: plan, verify, pause/resume/stop/status, limits
- [x] M6-01 Notch shape/springs/states/echo/approval/hover/badge/privacy dots (web)
- [x] M7-01 EN + HI strings for the notch

## Native foundation progress
- [x] M1-01a Native Python entry point and in-memory bound-approval primitive with portable tests and Windows CI configuration (CI not yet observed).

## ChatGPT provider
- [x] M3-05 Implement preliminary ChatGPT-plan OAuth and streamed Responses provider; fake cryptographic, callback, provider and CLI tests. Default online; live/Windows validation remains open.
- [ ] M3-06 Test real Windows DPAPI, ChatGPT sign-in and model tool calling; implement serialized rotating-token refresh, sign-out revocation and multiple accounts.
- [x] M3-07a Connect limited ChatGPT sign-in/text to a separate preview UI, with online-busy indication, dry run by default and best-effort cancellation.
- [ ] M3-07b Implement isolated workers, production safety gate and robust emergency stop; validate on Windows.

## Native text vertical slice
- [x] M1-01c Restricted local Ollama text request, typed single-tool registry, dry run, and Windows Notepad backend with foreground read-back; fakes and recorded loopback transport tests. Actual Windows and live-model verification outstanding.

## Connected native sandbox
- [x] M1-01b Connect Qt studio to versioned demo events, a background worker, in-memory fake tools, sandbox approvals and stop; cover the flow with tests. Not a real agent integration.

## UI-first native prototype
- [x] M6-02 Native visual-only Qt Quick notch studio, 10 synthetic states, reduce-motion toggle, offscreen captures and smoke test. Windows behavior and full M6 acceptance remain open.

## Open (not started unless noted)
- [ ] UI-01 Capture screenshots + frame times (script written, could not run here)
- [ ] M1-01 Python package `vox` (unification of Wyzer + Aemyos pieces); observe Windows CI. Approval primitive started in M1-01a; no tools or agent yet.
- [ ] M2-01 Real voice loop: Silero VAD, openWakeWord, Faster-Whisper, Piper, WASAPI loopback AEC, `vox bench`
- [ ] M2-02 Qt Quick production notch with verified Win32 flags (no-activate, click-through, fullscreen hide, DPI, hot-plug); prototype only exists
- [ ] M3-03 Socket-level offline guard + Windows Firewall test
- [ ] M3-04 Verify Claude/Ollama adapters against live endpoints
- [ ] M4-03 Missing tools: click_target/read_ui (vision→UIA), drag, scroll, zip/unzip, real Core Audio, CDP browser, Chrome extension path, find_installed index
- [ ] M4-04 Model acceptance suites (≥80% gate) + `MODEL_BENCH.md`
- [ ] M5-06 Speaker verification (flag only); real loopback correlation
- [ ] M7-02 Settings window (keys in Credential Manager), onboarding wizard, hardware probe, model downloader, Aemyos language set + parity test
- [ ] M8-01 PyInstaller/Nuitka + Inno Setup (online + offline), signing, `vox doctor`, soak tests, `LICENSES.md` review of wake-word/TTS voice licences. Online-only *preview* installer and installed-app offscreen smoke succeeded in Windows CI; full Windows test suite stalled and full acceptance remains open.

- [x] M8-01a Build unsigned per-user online-only early preview installer and verify packaged and installed Qt rendering offscreen in Windows Actions.
- [x] M8-02 Diagnose stalled Windows non-UI CI checks and verify Qt tests and complete suite on Windows. Done 2026-11-04: root causes were platform-specific mypy unused-ignore reports and oversized pytest parametrize IDs exceeding the Windows 32,767-char environment-variable limit; run 41881288166 is fully green on `windows-latest` (lint + all 8 test files). Fakes/offscreen Qt only — not live validation, and not an installer smoke substitute.

## Groq voice vertical slice
- [x] M2-03 User-supplied Groq API key in Windows DPAPI, bounded push-to-talk microphone capture, Groq Whisper transcription, Groq tool calling and optional Orpheus speech; fake contracts and Qt wiring tests.
- [x] M4-05 Fixed Windows Notepad, Calculator and Paint launch, plus HTTPS browser action with expiring bound click approval; dry-run option and fake backends.
- [x] M2-05 Hands-free wake word: on-device Vosk small-en “Hi Vox” spotting (no audio leaves the PC before the wake phrase), silence-endpointed request capture, automatic return to wake listening, approval pauses spotting; Record/Finish buttons replaced by a Hands-free toggle; fake-engine/controller/UI tests. Real-microphone accuracy validation folds into M2-04.
- [ ] M2-04 Validate real Windows microphone, wake-word accuracy, playback, live Groq key/model access, STT, tool calling and TTS end-to-end on a disposable PC (see `WINDOWS_TEST_CHECKLIST.md`).
- [x] M4-06a Implement safe folder opening (known folder aliases or validated absolute local paths, SHGetKnownFolderPath resolution, canonical path binding), text typing via SendInput Unicode, scroll, window management (minimize/maximize/restore/close), file operations (copy/move/delete), screenshots, and more built-in apps (Browser, Email, Settings, FileExplorer, Calendar, Photos, MediaPlayer) in an explicitly selected visible Windows window; argument-bound approval, control/bidi rejection, fake backend and Qt wiring tests.
- [x] M4-06a2 Add write-only clipboard (`set_clipboard`: exact text bound to single-use approval, control/bidi rejection, 1,000-char cap, checked Win32 `CF_UNICODETEXT` write) and read-only SAFE-tier `system_info` (Windows version/architecture/system-drive use; no user or host names). Clipboard reading intentionally not implemented: contents are untrusted, often contain secrets, and the native slice has no redaction/untrusted-output layer. Fake backend tests cover binding, tamper resistance, tier downgrade, and fail-closed planning.
- [ ] M4-06b Implement remaining PC control safely with production policy/audit, isolated cancellation and verified Windows backends; do not enable arbitrary shell or destructive tools prematurely.
- [ ] M8-03 Observe Groq installer and file-level Windows CI; test install/uninstall on clean Windows VM; sign and review dependency licensing.

## Live Command Engine (spec 2026-11-05; plan: `docs/LIVE_ENGINE_PLAN.md`)

- [x] LE0-01 Audit existing voice/turn stack with file paths; confirm turn construction & memory (measured: 2 messages, no history).
- [x] LE0-02 Voice-layer weakness list with per-phase disposition (`LIVE_ENGINE_PLAN.md` §3).
- [x] LE0-03 Module map (`vox/engine/` adapters) + state-storage decision (SQLite WAL under `%LOCALAPPDATA%\vox\session\`).
- [x] LE0-04 Baseline bench (`scripts/live_engine_baseline.py` → `artifacts/live_engine/baseline.json`): legacy 30-command replay, request shape, wake text-matcher FA/FR, matcher idle cost; audio/Groq/desktop metrics recorded `not_measured` with reasons.
- [x] LE0-05 Log reconciliation decisions L-01…L-10 + operational deviations in `DECISIONS.md`; existing suite recorded (161 passed, 1 skipped @ `1af9145`).
- [x] LE1-01 Timeline + extended events, Clock injection, turn manager (soft/hard endpointing, pre-roll, fragment merge, commit point, generations), control plane (L-02), cancellable TTS with spoken offset, virtual-clock replay harness. Done 2026-11-05: `vox/engine/` {config, clock, timeline, endpointing, i18n, control, turns} + WinsoundPlayer; replay edge cases 1, 2, 4, 5, 6, 14, 27 green in `tests/live_engine/`; cancel proven ≤150 ms in *virtual* time (player polls cancel every 20 ms; real winsound stop latency awaits Windows bench). Engine not yet wired into the app (LE4); `engine.mode` default legacy.
- [ ] LE1b-01 Two-stage "Hi Vox" wake (VAD gate + Vosk verify), phrase/alias config + EN/HI i18n, wake timeout, lock/mic-busy suspend, `trigger=wake`, privacy states, calibrate, Windows `vox bench --wake` corpus → SPEECH_BENCH.md.
- [ ] LE2-01 Contextualiser (code + small-model paths, A/B per L-01), entity registry, glossary, STT prompt + `verbose_json` confidence, phonetic repair, HI/Hinglish.
- [ ] LE3-01 Memory layers: user card, preferences sheet, device index (BM25 + phonetic; vectors if licence-clean), SQLite session store + restore, delete-session-data, settings editors.
- [ ] LE4-01 Prompt v2 + cache-ordered assembly, streaming chat with early T0 dispatch, meta-tools (ask_clarification/stay_silent/show_card), canned acks/earcons, notch/hover UI states.
- [ ] LE5-01 Background memory writer, task stack, desktop input lock, undo as ordinary tools, dictation mode.
- [ ] LE6-01 Per-turn fallback (+ optional hedging if bench-validated), stage timers + debug waterfall, screen_note attach.
- [ ] LE7-01 Full verification (36 edge cases, red-team, offline guard, soak incl. 2 h ambient wake), A/B vs LE0 baseline; flip default to `live` + delete legacy only on parity-or-better; write `docs/LIVE_ENGINE_REPORT.md`.
