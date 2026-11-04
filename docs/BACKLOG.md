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
- [ ] M8-02 Diagnose stalled Windows non-UI CI checks and verify Qt tests and complete suite on Windows; do not treat installer smoke as a complete test pass.

## Groq voice vertical slice
- [x] M2-03 User-supplied Groq API key in Windows DPAPI, bounded push-to-talk microphone capture, Groq Whisper transcription, Groq tool calling and optional Orpheus speech; fake contracts and Qt wiring tests.
- [x] M4-05 Fixed Windows Notepad, Calculator and Paint launch, plus HTTPS browser action with expiring bound click approval; dry-run option and fake backends.
- [ ] M2-04 Validate real Windows microphone, playback, live Groq key/model access, STT, tool calling and TTS end-to-end on a disposable PC.
- [x] M4-06a Implement safe folder opening (known folder aliases or validated absolute local paths, SHGetKnownFolderPath resolution, canonical path binding), text typing via SendInput Unicode, scroll, window management (minimize/maximize/restore/close), file operations (copy/move/delete), screenshots, and more built-in apps (Browser, Email, Settings, FileExplorer, Calendar, Photos, MediaPlayer) in an explicitly selected visible Windows window; argument-bound approval, control/bidi rejection, fake backend and Qt wiring tests.
- [ ] M4-06b Implement remaining PC control safely with production policy/audit, isolated cancellation and verified Windows backends; do not enable arbitrary shell or destructive tools prematurely.
- [ ] M8-03 Observe Groq installer and file-level Windows CI; test install/uninstall on clean Windows VM; sign and review dependency licensing.
