# LICENSES (draft)

## This build (npm)
next, react, react-dom, drizzle-orm, pg, dotenv, zod — MIT. tailwindcss, @tailwindcss/postcss — MIT. TypeScript — Apache-2.0. Verify with `npx license-checker` before distribution.

## Upstream code
Aemyos (MIT, © 2026 Aemyos) and Wyzer-AI (MIT, © 2026 XtraWyze). No upstream source is copied into this repo; designs (typed registry, bound approvals, evidence-based tasks) are re-implemented. See `NOTICE.md`.

## For the Windows build (NOT yet reviewed — do not ship before checking)
| Component | Concern |
|---|---|
| openWakeWord pretrained models | Several are CC BY-NC-SA / research-only; Wyzer's `hey_Wyzer.onnx` terms unknown. Train own model or review per file. |
| Silero VAD | MIT. |
| Faster-Whisper / Whisper weights | MIT code / MIT weights (OpenAI); check CTranslate2 conversions. |
| Piper voices | Per-voice licences vary (some CC BY-NC); Kokoro (Wyzer) Apache-2.0 code, check voices. |
| Edge TTS | Unofficial Microsoft endpoint; ToS risk for redistribution — keep as optional online provider. |
| PySide6 | LGPL-3 — dynamic linking only; PyInstaller bundling needs LGPL compliance notice. |
| Ollama / models (Qwen etc.) | Ollama MIT; each model has its own licence. |
| pywinauto, comtypes, pycaw, winsdk | MIT/BSD-like; verify. |
