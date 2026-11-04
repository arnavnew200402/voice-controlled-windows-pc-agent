# Vox — Windows voice control (early access)

Vox now has a **real Groq-powered push-to-talk path**, not a simulated provider. It is not yet a complete general-purpose Windows agent: the enabled actions are opening Notepad, Calculator, Paint, HTTPS websites, local folders, and typing exact text into a user-selected visible window. Website, folder and typing actions require explicit click approval. No general shell, file deletion, arbitrary app launch, screen reading or computer-use tools are enabled.

## Run the Groq voice UI

On Windows 10/11 x64 with Python 3.11+:

```powershell
python -m pip install -e ".[ui,voice]"
python -m vox --ui
```

1. Paste your own Groq API key **into the app**, then click Save key. Never put the key in chat or commit it to a repository. The app stores it encrypted with Windows DPAPI for the current user under `%LOCALAPPDATA%\vox\groq.key`. The Remove button deletes the saved key; revoke it at Groq if necessary. Uninstall preserves user data.
2. Click **Start recording**, speak, then **Finish recording**. It automatically ends after 15 seconds. Or type a request. Enable Dry run to plan without taking action.
3. Approve or decline any displayed website address, folder path or typing request. For typing, select the exact target window from a locally enumerated list; window titles are never sent to Groq. Approval expires after 15 seconds and cannot be reused. Voice cannot approve an action.

The microphone is not continuously listening; recorded audio is held in memory and sent to Groq for transcription. The transcript, text request, and tool definitions are sent to Groq. Optional spoken replies are also sent to Groq for synthesis. No screen capture is sent. Groq use requires connectivity, an eligible key/model/quota, and may incur charges. The defaults are `whisper-large-v3-turbo`, `openai/gpt-oss-20b`, and `canopylabs/orpheus-v1-english`. See [Groq speech-to-text](https://console.groq.com/docs/speech-to-text), [tool use](https://console.groq.com/docs/tool-use), and [text-to-speech](https://console.groq.com/docs/text-to-speech).

**Live Groq calls, microphone capture/playback, Windows DPAPI and actual Windows actions have not yet been tested end-to-end.** Cancellation is cooperative and cannot undo an action already started or immediately interrupt all network calls/audio playback. There is no wake word, acoustic loopback verification, general automation, production audit/policy, isolated worker, offline mode or clean-VM validation. Only use a trusted disposable test PC until those gaps are closed.

The [Windows Groq installer run](https://github.com/arnavnew200402/voice-controlled-windows-pc-agent/actions/runs/41861807832) has an artifact (`vox-windows-groq-early-access`), but the run status remains ambiguous; check `docs/STATE.md` and the run before treating it as a verified complete build. It predates the folder/typing changes. Installers are unsigned. The older ChatGPT/Notepad preview artifact is not the Groq build.

## Other project paths

The old `python -m vox --ui-demo` design studio remains a developer-only simulated harness; it is not the Groq application. The previous ChatGPT OAuth / Ollama **text-only** command-line paths remain experimental and separate; they are not used by the Groq UI. The web app is a reference implementation against a virtual PC, not the Windows agent.

## Checks

```powershell
python -m pip install -e ".[dev,ui,voice]"
python -m pytest -m "not desktop" -q
python -m ruff check vox tests scripts/capture_native_ui.py scripts/windows_entry.py scripts/collect_preview_licenses.py
python -m ruff format --check vox tests scripts/capture_native_ui.py scripts/windows_entry.py scripts/collect_preview_licenses.py
python -m mypy
```

See `docs/STATE.md`, `docs/BACKLOG.md`, `docs/BLOCKERS.md`, `docs/DECISIONS.md`, and `docs/ARCHITECTURE.md` for scope and remaining acceptance criteria.
