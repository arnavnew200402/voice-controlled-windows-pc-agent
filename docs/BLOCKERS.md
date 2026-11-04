# BLOCKERS

1. **Windows-native stack cannot run in this sandbox** (Linux, no display, no Windows APIs). Attempts: n/a (hard constraint). Fallback shipped: verifiable web/TypeScript reference + docs for the port.
2. **Headless browser could not launch for screenshots.** Attempt 1: `npx playwright install chromium` succeeded. Attempt 2: launch failed with `libnspr4.so` missing. Attempt 3: `apt-get install` (no root) and `apt-get download` (no package sources) both failed. Fallback: `scripts/ui-capture.mjs` committed unrun; no frame-time numbers claimed.
3. **Upstream Wyzer tests give no clean baseline on Linux** (31 failures from Windows-only backends). Needs `windows-latest`.
4. **Python `venv`/`ensurepip` unavailable** in the sandbox; tests were run with `pip --break-system-packages` into the sandbox's own Python (outside this repo).
