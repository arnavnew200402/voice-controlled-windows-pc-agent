# STATE

**Milestone:** Real Groq voice vertical slice in progress. The complete voice-first Windows agent and M1–M8 exit criteria remain unmet. The user changed provider priority from ChatGPT OAuth to Groq API key.

## Done
- Existing web reference and native simulation remain developer-only. The installed native UI is now connected to real (not simulated) Groq push-to-talk services.
- User-entered Groq key is DPAPI-protected per Windows account, removable in UI, never logged; no real key used in tests.
- Explicit, bounded 15-second microphone capture to memory, Groq Whisper STT, Groq chat tool calling and optional Orpheus TTS/WAV playback. Recording and network activity have visible indicators; no continuous listening or screen capture. TTS runs only after recording closes.
- Closed action registry: Notepad, Calculator, Paint and HTTPS websites. Websites require a single-use, argument-bound 15-second click approval; dry run available. Model-supplied paths, shell commands, arbitrary apps and unsupported tools are rejected.
- Linux 2026-11-04: **90 passed, 1 Windows-only DPAPI skipped**; Ruff, formatting, mypy and Qt offscreen startup smoke passed, using fakes and no real network/microphone/desktop actions. Screenshot: `artifacts/ui/native/groq-voice.png` (Linux offscreen, not Windows evidence).
- Windows Groq installer workflow prepared; **new build result pending**. Older ChatGPT-only preview artifact is not a Groq installer.

## In progress / limitations
- No end-to-end live Groq, microphone, TTS, DPAPI or desktop validation on Windows. Groq model access, quotas and costs depend on the user's account. Sandbox cannot reach Groq.
- The voice flow is push-to-talk only; no wake word, loopback verification, speaker verification, persistent task engine, general PC automation, production audit, protected policy integration, isolated workers or offline mode. Website approval is local UI click, not a verified physical-input security boundary.
- Stop is cooperative and cannot undo actions already started or immediately preempt all network calls/playback; website approval is revoked on stop.
- The existing Windows non-UI CI repeatedly hung. New per-file matrix is a different diagnostic approach; results pending. The installer build job is independent; packaging success must not be presented as a test-suite pass.
- Prior ChatGPT and Ollama CLI paths are separate and experimental; no OAuth refresh/revocation. The old fake studio remains accessible only as a developer harness.
- Full installer/signing/legal review, clean-VM install/uninstall, safety/red-team/benchmark, real Windows DPI/focus, and milestone acceptance remain open. No merge to main before required exit criteria pass.

## Next 5 tasks
1. Observe new Windows matrix and Groq installer build; diagnose any failures without treating smoke tests as live validation.
2. Test Groq key storage, microphone permissions, live transcription/chat/TTS, playback and the supported app actions on a disposable Windows 10/11 system with user-provided authorized key.
3. Build a reviewed, argument-bound policy/audit and cancellation isolation before broadening desktop, browser and file tools; extend tests including prompt injection and approvals.
4. Implement remaining task engine, voice/wake-word/audio loopback protections, robust hotkeys, full Windows integration, and honest capability reporting.
5. Complete offline mode, model acceptance benchmarks, installer signing/legal review, clean-VM install/uninstall, soak and desktop tests before merging.

## Blockers
No Windows desktop or microphone here; outbound sandbox access excludes Groq. GitHub Actions artifacts cannot be downloaded into the workspace because their storage host is outside the allowlist. See `BLOCKERS.md`.

## Commands
Windows Python 3.11+:
```powershell
python -m pip install -e ".[dev,ui,voice]"
python -m vox --ui
python -m pytest -m "not desktop" -q
python -m ruff check vox tests scripts/capture_native_ui.py scripts/windows_entry.py scripts/collect_preview_licenses.py
python -m ruff format --check vox tests scripts/capture_native_ui.py scripts/windows_entry.py scripts/collect_preview_licenses.py
python -m mypy
```
Linux sandbox: `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software VOX_REQUIRE_UI_TESTS=1 LD_LIBRARY_PATH=.python-deps/qt-libs/runtime PYTHONPATH=.python-deps python -m pytest -m 'not desktop' -q`. Offscreen entry smoke: `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software LD_LIBRARY_PATH=.python-deps/qt-libs/runtime PYTHONPATH=.:.python-deps python scripts/windows_entry.py --smoke-test`. `.python-deps` contains scratch-only dependencies and is not shipped.
