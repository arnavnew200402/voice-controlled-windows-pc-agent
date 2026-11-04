# STATE

**Milestone:** Experimental M3/M8 online-only text preview in progress. M1–M8 full-agent exit criteria remain unmet. ChatGPT is the current default; Ollama is deferred.

## Done
- Web reference implementation and simulation, native notch studio and sandbox are documented separately.
- Experimental ChatGPT-plan OAuth, Windows DPAPI store and streamed Responses provider; restricted T0 Notepad-only text registry with dry run. Real OpenAI and Windows use remain unverified.
- Separate actual online preview UI (`--ui`) connects browser sign-in and typed requests to that restricted path. It discloses online use, enables dry run by default and implements cooperative stop (not an isolated worker). `--ui-demo` remains simulated.
- Screenshot: `artifacts/ui/native/online-preview.png`, captured with Linux offscreen software rendering; not Windows or GPU evidence.
- 2026-11-04 Linux: **68 passed, 1 Windows-only DPAPI skipped**; Ruff, format check, mypy and Python-entry Qt offscreen smoke passed. Tests use fake provider/credentials; no real Notepad launch.
- Windows x64 per-user Inno Setup/PyInstaller preview workflow configured. First Windows CI run was cancelled after tests hung for over three minutes; follow-up adds per-test timeouts and splits test steps; build result pending.

## In progress / limitations
- Full voice, general PC control, production approvals/policy/audit, isolated workers, socket-level offline guard and complete installer acceptance criteria do not exist.
- Cooperative stop is best-effort: an already-started action cannot be undone and network calls can run until timeout; window closure does not guarantee instantaneous cancellation.
- No real Windows/OpenAI/DPAPI/Notepad verification, live plan validation, token refresh, app-side logout/revocation, or account switching. Sign in again on expiry; disconnect access in ChatGPT settings. Windows CI build is pending.
- Installer is unsigned, online-only and explicitly labeled early preview; legal packaging notices included but distribution compliance still needs independent review. Not a release of the full agent.

## Next 5 tasks
1. Observe Windows CI tests and packaged/installed smoke tests; provide artifact only if build succeeds.
2. Test the installer, DPAPI, SIWC sign-in, inference, Notepad and uninstall on a clean Windows 10/11 VM using an authorized test account.
3. Add serialized OAuth refresh, revocation/sign-out and account management with adversarial tests.
4. Integrate production policy/audit and isolated workers with verified emergency stop before expanding desktop tools.
5. Implement and validate voice, offline guard, Windows UI behavior, model benchmarks, signing and full installer acceptance.

## Blockers
This environment is Linux, cannot access OpenAI endpoints, and cannot verify real Windows desktop/GPU behavior or live account entitlement. Windows hosted workflow availability and an authorized clean VM remain necessary. See `BLOCKERS.md`.

## Commands
Windows Python 3.11+:
```powershell
python -m pip install -e ".[dev,ui]"
python -m vox --ui
python -m vox --login
python -m vox --text "Open Notepad" --dry-run
python -m vox --ui-demo
python -m pytest -m "not desktop" -q
python -m ruff check vox tests scripts/capture_native_ui.py scripts/windows_entry.py scripts/collect_preview_licenses.py
python -m ruff format --check vox tests scripts/capture_native_ui.py scripts/windows_entry.py scripts/collect_preview_licenses.py
python -m mypy
```
Linux sandbox tests: `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software VOX_REQUIRE_UI_TESTS=1 LD_LIBRARY_PATH=.python-deps/qt-libs/runtime PYTHONPATH=.python-deps python -m pytest -m 'not desktop' -q`. Smoke: `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software LD_LIBRARY_PATH=.python-deps/qt-libs/runtime PYTHONPATH=.:.python-deps python scripts/windows_entry.py --smoke-test`. Scratch libraries under `.python-deps` are not shipped. Windows build commands are in `.github/workflows/windows-preview-installer.yml`. Login and requests require online ChatGPT plan consent; `--provider ollama --model YOUR_MODEL` selects the deferred local CLI path.
