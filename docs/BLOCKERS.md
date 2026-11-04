# BLOCKERS

1. **Windows-specific integration cannot run in this sandbox** (Linux, no Windows APIs). Portable PySide6/QML now runs offscreen with scratch-only runtime libraries; this is not a substitute for testing focus, hit-testing, display behavior or performance on Windows.
2. **Headless browser could not launch for screenshots.** Attempt 1: `npx playwright install chromium` succeeded. Attempt 2: launch failed with `libnspr4.so` missing. Attempt 3: `apt-get install` (no root) and `apt-get download` (no package sources) both failed. Fallback: `scripts/ui-capture.mjs` committed unrun; no frame-time numbers claimed.
3. **Upstream Wyzer tests give no clean baseline on Linux** (31 failures from Windows-only backends). Needs `windows-latest`.
4. **Python `venv`/`ensurepip` unavailable** in the sandbox; tests were run with `pip --break-system-packages` into the sandbox's own Python (outside this repo).

5. Native Qt offscreen launch initially lacked system graphics libraries. Scratch-only copies were obtained for Linux smoke tests; they are not shipped. A real Windows desktop run and GPU performance measurements remain outstanding.
6. ChatGPT OAuth/Responses live endpoints and Windows DPAPI are unavailable in this Linux sandbox. Fakes and generated keys exercise the contracts; a Windows live-account test is still required. No real credentials were requested or stored here.
