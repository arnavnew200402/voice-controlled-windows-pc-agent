# STATE

**Milestone:** Real Groq voice vertical slice in progress. Folder opening, safe text typing, scroll, window management (minimize/maximize/restore/close), file operations (copy/move/delete), screenshots, clipboard write (exact approved text only; the clipboard is never read), read-only system info, and more built-in apps now implemented and fake-tested. The complete voice-first Windows agent and M1–M8 exit criteria remain unmet. The user changed provider priority from ChatGPT OAuth to Groq API key.

## Done
- Existing web reference and native simulation remain developer-only. The installed native UI is now connected to real (not simulated) Groq push-to-talk services.
- User-entered Groq key is DPAPI-protected per Windows account, removable in UI, never logged; no real key used in tests.
- Explicit, bounded 15-second microphone capture to memory, Groq Whisper STT, Groq chat tool calling and optional Orpheus TTS/WAV playback. Recording and network activity have visible indicators; no continuous listening or screen capture. TTS runs only after recording closes.
- Closed action registry: Notepad, Calculator, Paint, Browser, Email, Settings, FileExplorer, Calendar, Photos, MediaPlayer, HTTPS websites, known/absolute local folders, exact text typing, scroll, window management (minimize/maximize/restore/close), file operations (copy/move/delete), screenshots, clipboard write of exact approved text (clipboard reads are not implemented by design), and read-only system information. All consequential actions require single-use, argument-bound approval. Websites, folders and typing require single-use, argument-bound 15-second click approval; dry run available. Model-supplied paths, shell commands, arbitrary apps, control/bidi characters and unsupported tools are rejected. Window titles and handles are never sent to Groq; the user selects the target locally.
- Linux 2026-11-04: **126 passed, 1 Windows-only DPAPI skipped**; Ruff, formatting, mypy and Qt offscreen startup smoke passed, using fakes and no real network/microphone/desktop actions. Screenshots: `artifacts/ui/native/groq-voice.png`, `artifacts/ui/native/groq-voice-folder-typing.png` (Linux offscreen, not Windows evidence).
- Windows Groq installer run [41861807832](https://github.com/arnavnew200402/voice-controlled-windows-pc-agent/actions/runs/41861807832) remained **queued** after more than 10 minutes, so no new Groq installer has been produced. The older ChatGPT-only preview artifact is not a Groq installer.

## In progress / limitations
- No end-to-end live Groq, microphone, TTS, DPAPI or desktop validation on Windows. Groq model access, quotas and costs depend on the user's account. Sandbox cannot reach Groq.
- The voice flow is push-to-talk only; no wake word, loopback verification, speaker verification, persistent task engine, general PC automation beyond the named registry, production audit, protected policy integration, isolated workers or offline mode. Website, folder, typing, scroll, window-management, and file-operation approval are local UI clicks, not verified physical-input security boundaries. Window foreground/focus can change between selection and SendInput; results report that honestly.
- Stop is cooperative and cannot undo actions already started or immediately preempt all network calls/playback; website approval is revoked on stop.
- The Groq installer workflow run 41866123354 completed successfully on commit `bbc8f96` (folder/typing work), with artifact `13343185262` (`vox-windows-groq-early-access`). This predates the scroll/window-management addition. A subsequent installer run for the latest commit is queued (run 41867174186). Installer smoke tests do not validate live Groq, microphone, DPAPI or real desktop actions.
- The existing Windows non-UI CI repeatedly hung. In the new per-file matrix (run 41861807607), the Groq fake-test step completed successfully on Windows, but its job remained in progress even after its Complete job step; other matrix jobs were queued. The run was force-cancelled to free capacity, with no overall Windows-suite conclusion. The installer job remained queued. Packaging success would not be a live validation or full test-suite pass.
- Prior ChatGPT and Ollama CLI paths are separate and experimental; no OAuth refresh/revocation. The old fake studio remains accessible only as a developer harness.
- Full installer/signing/legal review, clean-VM install/uninstall, safety/red-team/benchmark, real Windows DPI/focus, and milestone acceptance remain open. No merge to main before required exit criteria pass.

## Next 5 tasks
1. Observe new Windows matrix and Groq installer build for the folder/typing changes; diagnose any failures without treating smoke tests as live validation.
2. Test Groq key storage, microphone permissions, live transcription/chat/TTS, playback and the supported app, folder and typing actions on a disposable Windows 10/11 system with user-provided authorized key.
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
