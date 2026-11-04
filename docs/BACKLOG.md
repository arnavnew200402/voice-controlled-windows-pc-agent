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

## Open (not started unless noted)
- [ ] UI-01 Capture screenshots + frame times (script written, could not run here)
- [ ] M1-01 Python package `vox` (unification of Wyzer + Aemyos pieces); CI on Windows
- [ ] M2-01 Real voice loop: Silero VAD, openWakeWord, Faster-Whisper, Piper, WASAPI loopback AEC, `vox bench`
- [ ] M2-02 Qt Quick notch with Win32 flags (no-activate, click-through, fullscreen hide, DPI, hot-plug)
- [ ] M3-03 Socket-level offline guard + Windows Firewall test
- [ ] M3-04 Verify Claude/Ollama adapters against live endpoints
- [ ] M4-03 Missing tools: click_target/read_ui (vision→UIA), drag, scroll, zip/unzip, real Core Audio, CDP browser, Chrome extension path, find_installed index
- [ ] M4-04 Model acceptance suites (≥80% gate) + `MODEL_BENCH.md`
- [ ] M5-06 Speaker verification (flag only); real loopback correlation
- [ ] M7-02 Settings window (keys in Credential Manager), onboarding wizard, hardware probe, model downloader, Aemyos language set + parity test
- [ ] M8-01 PyInstaller/Nuitka + Inno Setup (online + offline), signing, `vox doctor`, soak tests, `LICENSES.md` review of wake-word/TTS voice licences
