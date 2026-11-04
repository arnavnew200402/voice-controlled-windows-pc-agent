# Vox — voice-controlled PC agent (web reference build)

A voice-first agent with a Glance-style virtual notch, a tiered safety model with argument-bound approvals, a health-aware offline/online provider router, and a red-team suite — running against a **sandboxed virtual PC** (Postgres-backed). This is the platform-independent core of the Windows agent described in the brief; the Windows-native parts are not built (see `docs/FINAL_REPORT.md`).

```
npm run build && npx next start      # http://localhost:3000
curl -X POST localhost:3000/api/redteam
```

Docs: `docs/AUDIT.md`, `ARCHITECTURE.md`, `SAFETY.md`, `UI_SPEC.md`, `DECISIONS.md`, `STATE.md`, `BACKLOG.md`, `BLOCKERS.md`, `LICENSES.md`, `FINAL_REPORT.md`. System prompt: `prompts/system.md`.
