# STATE

**Milestone:** web reference build complete (covers M0, M5 reference, M3 reference, M4-lite, M6-web). Windows native milestones not started.

## Done (verified by running)
- M0 audit: `AUDIT.md` (both upstream suites actually run; results recorded).
- Safety: tiers, escalation, bound approvals, redaction, audit log — **25/25 red-team cases pass** (`artifacts/redteam.json`).
- Router: hysteresis, mid-task failover (RT-22), offline guard counters (RT-21).
- Tools: ~45 tools on a Postgres virtual PC with evidence read-back.
- Notch UI: SVG shape with concave ears, spring animation, 10 states, echo HUD, approval card, hover panel, mode badge, privacy dots, reduce-motion, EN/HI strings.
- `npx next typegen`, `tsc --noEmit`, `npm run build`, `build_and_start` pass (see FINAL_REPORT).

## Not verified / not done
- No browser screenshots or frame-time numbers: headless Chromium could not launch (missing system libs, no root). `scripts/ui-capture.mjs` is ready to run elsewhere.
- Everything Windows-native (see `BACKLOG.md`).

## Next 5 tasks
1. Run `scripts/ui-capture.mjs` on a machine with a browser; commit screenshots + frame times to `artifacts/ui/`.
2. Start the Python `vox` package from Wyzer: port `policy.py`, `approvals.py`, `redact.py` 1:1 and the red-team suite.
3. Qt Quick notch from `UI_SPEC.md`.
4. Socket-level offline guard + firewall test.
5. Windows CI (`windows-latest`) running upstream suites for a real baseline.

## Commands
```
npm run build && npx next start          # app
curl -X POST localhost:3000/api/redteam  # red-team suite (resets sandbox)
npx tsc --noEmit                         # types
PW=<playwright index.mjs> node scripts/ui-capture.mjs   # UI harness
```
