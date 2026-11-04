# Vox — voice-controlled PC agent (web reference build)

A voice-first agent with a Glance-style virtual notch, a tiered safety model with argument-bound approvals, a health-aware offline/online provider router, and a red-team suite — running against a **sandboxed virtual PC** (Postgres-backed). This is the platform-independent core of the Windows agent described in the brief; the complete Windows-native agent is not built (see `docs/FINAL_REPORT.md`).

```
npm run build && npx next start      # http://localhost:3000
curl -X POST localhost:3000/api/redteam
```

Docs: `docs/AUDIT.md`, `ARCHITECTURE.md`, `SAFETY.md`, `UI_SPEC.md`, `DECISIONS.md`, `STATE.md`, `BACKLOG.md`, `BLOCKERS.md`, `LICENSES.md`, `FINAL_REPORT.md`. System prompt: `prompts/system.md`.

## Native foundation (early work)

The Python package is not a functioning desktop agent yet. To run its portable checks with Python 3.11+:

```
python -m pip install -e ".[dev,ui]"
python -m vox
python -m pytest -m "not desktop"
python -m ruff check vox tests
python -m ruff format --check vox tests
python -m mypy
```

The approval module must not be used for real PC actions until its integration prerequisites in `docs/ARCHITECTURE.md` are met.

## Native notch design studio

On Windows with Python 3.11 or newer:

```powershell
python -m pip install -e ".[ui]"
python -m vox --ui-demo
```

Choose a state in the studio to preview the notch at the top of the primary work area. The studio also runs two connected in-memory simulations, including a sandbox approval and stop. The waveform and all simulated actions are synthetic; **no microphone, real PC actions, production approvals or settings are connected**. The entire demo notch is click-through; use the separate studio to change states and close the studio to exit. Windows behavior has not yet been verified. Offscreen captures are in `artifacts/ui/native/`.

To run the Python checks including Qt, install `.[dev,ui]` instead. To refresh captures on a desktop, run `python scripts/capture_native_ui.py` from the repo root. Frame intervals from an offscreen software renderer are not evidence of Windows GPU performance.

## Experimental online text command (ChatGPT)

On Windows, sign in with your ChatGPT account in the system browser and consent to ChatGPT plan usage. The exact request text and the small available tool schema are sent to OpenAI; no screenshot, audio, clipboard or file content is sent by this path. Usage and model availability depend on your ChatGPT plan and OpenAI's preview policies.

```powershell
python -m pip install -e ".[ui]"
python -m vox --login
python -m vox --text "Open Notepad" --dry-run
# Only after reviewing the dry run:
python -m vox --text "Open Notepad"
```

A separate, limited real preview can be started with `python -m vox --ui`. Its browser sign-in and text request controls connect to this same Notepad-only path; dry run is checked by default. The visual design studio (`--ui-demo`) remains a sandbox. Stop is best-effort and cannot undo an action already started. The preview has no voice or general PC control. A per-user Windows installer build is defined in `.github/workflows/windows-preview-installer.yml`; consult `docs/STATE.md` for the latest observed build status.

The default provider is ChatGPT, using the official Sign in with ChatGPT open-source flow and Responses API, not browser cookies or an API key. Tokens are encrypted using Windows DPAPI and stored under `%LOCALAPPDATA%\vox\chatgpt.dat`. The default model is the first visible model in the account's returned model list; use `--model MODEL` to choose another. **Live OAuth, ChatGPT inference, DPAPI and the Windows launcher have not been verified on Windows.** The implementation currently supports one saved account and does not automatically refresh tokens or revoke on sign-out; when the session expires, rerun `--login`. To revoke access, disconnect the app in ChatGPT settings. The separate simulated notch studio does not use this provider.

This path only supports Notepad. It is not the full voice agent and does not provide the full offline guarantee or isolated-worker cancellation. OpenAI's [ChatGPT plan usage documentation](https://developers.openai.com/siwc/token-sharing-open-source) describes eligibility and current preview restrictions.

## Deferred local text command (Ollama)

This separate native path can ask an **installed, tool-capable Ollama model** to open Windows Notepad. It exposes no other PC actions, and it does not use the UI demo, speech or cloud providers. No default model has passed an acceptance benchmark yet.

```powershell
# Use the name of a tool-capable model already installed in Ollama.
python -m vox --provider ollama --text "Open Notepad" --model YOUR_MODEL --dry-run
# Only on Windows, after reviewing the dry-run:
python -m vox --provider ollama --text "Open Notepad" --model YOUR_MODEL
```

The transport uses `127.0.0.1:11434` by default (`--ollama-port` changes only the port), does not use a proxy or follow redirects, and sends the request to the local model. The Windows launcher uses the Windows system directory rather than a model-supplied command or path. It reports success only when the launched process remains alive and owns the foreground window; newer Notepad versions can delegate to another process, in which case it reports that the result could not be verified. This path has only been tested with fakes and a recorded local HTTP server, **not on Windows or against a live model**. It does not provide the specified socket-level offline guarantee, cancellation, full safety model, voice or installer.
