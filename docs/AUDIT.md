# M0 Audit — Aemyos (`desktop-agent-ai`) and Wyzer-AI

Both repos were shallow-cloned into a scratch directory outside this repo and read. Nothing from them is vendored here.
Commits audited: Aemyos `250c878`, Wyzer `db83c08` (0.3.1). Both MIT.

## Aemyos (`YSah44/desktop-agent-ai`)
| Item | Finding |
|---|---|
| Entry / model | `main.py` (single large module) + `config.py` + `services/` (~30 modules). Thread-based; overlay window, tray (`pystray`). |
| Audio | `sounddevice` capture → **cloud** STT (Groq / OpenRouter). No local VAD/wake/STT. `speaker_tap.py`, `busy_audio.py` handle mic-while-speaking. |
| Providers | Anthropic (reasoning + vision), Groq (STT), OpenRouter (alt), Edge TTS via `pygame`. All cloud; **no offline path**. |
| Tools | Large `execute_funcs.py` / `desktop_commands.py` (apps, clicks, typing, Explorer, Settings, lock/sleep), UIA (`win_uia.py`), OCR via `winsdk`, optional Chrome extension bridge (`websockets`). |
| Safety | `services/safety.py`: regex guards for shutdown/delete/recycle/send/purchase; `loop_guard.py`. Confirmation is by key names in tool args (`confirmed`, `explicit`…) — **model-controlled, not bound to args, no expiry**. |
| UI | Overlay face (`face_id.py`, `generate_face.py`). No notch concept. |
| Packaging | `aemyos.spec` (PyInstaller), `installer.iss` (Inno Setup), `sign.bat` + `signing.example.json`. |
| Tests | `test_destructive_guards.py`, `test_i18n_parity.py`, `test_run.py`. **Run result here:** guards file = 86 tests, 1 failure + 36 errors, all from missing Windows/audio deps (`sounddevice`, etc.) on Linux; i18n parity script exited 0 with no output. |
| Weak spots | Regex-based destructive-action detection (`_CLICK_DESTRUCTIVE`, shell substring list) is bypassable; one `subprocess.Popen(..., shell=True)` in `pc_context.py:146`; confirmation not argument-bound; monolithic files. |
| Secrets scan | No real keys found; matches were test fixtures (`sk-ant-test`, `gsk_should_not_use`). |
| Licences | MIT. Deps: pyautogui, Pillow, opencv-headless, numpy, requests, pyperclip, pynput, sounddevice, edge-tts (uses an unofficial Microsoft endpoint — ToS risk), pygame, websockets, comtypes, pywinauto, winsdk, pystray. |

## Wyzer-AI (`XtraWyze/Wyzer-AI`)
| Item | Finding |
|---|---|
| Entry / model | `wyzer.app.cli:main` (`wyzer`), Qt UI with `--ui --voice`. Isolated workers + event ledger (`wyzer/events/ledger.py`). |
| Audio | openWakeWord (`openwakemodels/hey_Wyzer.onnx`, `hey_wiser.onnx`, 408 KB), `sounddevice`, Faster-Whisper, Kokoro TTS; optional `pycaw`/`comtypes` Core Audio. |
| Providers | Ollama-first LLM with native tool calling (`wyzer/brain/providers.py`, `factory.py`). |
| Tools | Pydantic `ToolRegistry` (`wyzer/tools/registry.py`, 11 packs). Model sees only registered tools; `UNKNOWN_TOOL` / `INVALID_TOOL_ARGUMENTS` returned as structured results. |
| Safety | `wyzer/policy/confirmations.py`: tool metadata `never/always/conditional`; approvals store the exact validated tool + args, SHA-256, step id, expiry. Sensitive visible text removed from scene context. **No tier model, no hard-confirm, no protected-path policy, no voice-injection defence.** |
| Task engine | Silent plans, step verification from tool evidence, persisted atomically, recovered as paused. |
| Tests | `tests/` ~366 collected; **31 failed on Linux**, the failures are dominated by Windows-only backends (`ToolExecutionError: WINDOWS_REQUIRED`, e.g. `test_windows_tools.py`) and Windows-pinned registry expectations. Remaining ≈335 pass. Needs a Windows CI run for a trustworthy baseline. |
| Licences | MIT. Deps: pydantic, psutil, playwright, pyperclip, send2trash, pywinauto, pillow, winrt-*, numpy, openwakeword, sounddevice, faster-whisper, kokoro; optional PySide6 (LGPL), pycaw, comtypes. **Wake-word models and Kokoro voices need individual licence review before redistribution** (`NOTICE.md` upstream says so). |
| Weak spots | Linux-hostile tests; large module surface; no explicit offline guard. |

## Conclusions that drive the architecture
1. Wyzer is the right spine (typed registry, bound approvals, evidence-based task engine). Aemyos contributes provider adapters, destructive-guard *test cases*, i18n parity idea, signing flow.
2. Neither repo has the tier model, argument-level escalation, T2 physical-confirm, offline socket guard, voice-injection defence or hysteresis router that the spec requires. Those were designed fresh (see `SAFETY.md`).
3. Aemyos' regex destructive-action detection must not be ported; it is replaced by tool-assigned tiers + argument-level escalation.
4. **Environment limit:** this sandbox is Linux; the Windows-native stack (PySide6/QML, Win32 flags, UIA, Core Audio, WASAPI loopback AEC, Silero/openWakeWord/Faster-Whisper/Piper) cannot be built or verified here. See `FINAL_REPORT.md`.
