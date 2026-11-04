# Architecture (as built)

Product name lives in one constant: `src/lib/vox/constants.ts` (`APP_NAME`).

```
 Browser (React)                              Next.js server (Node)                         Postgres
 ┌────────────────────────┐   NDJSON events   ┌──────────────────────────────────────┐      ┌──────────────┐
 │ Notch.tsx (SVG+springs)│ ◄──────────────── │ POST /api/turn → engine.runTurn()     │ ───► │ audit_log    │
 │ useVox (reducer = view │                   │   brain.routedChat (router+failover) │      │ event_log    │
 │ model, mic, TTS, keys) │ ── approvals ───► │   policy.classify → approvals.ts     │      │ vpc_files    │
 │ panels (PC/Audit/...)  │   /api/approvals  │   tools.ts (typed registry, evidence)│      │ vpc_state    │
 └────────────────────────┘                   │   redact.ts / netguard.ts             │      │ tasks        │
                                              └──────────────────────────────────────┘      │ memories     │
```

## Modules (`src/lib/vox`)
| File | Role |
|---|---|
| `events.ts` | Versioned event models (spec 3.2): StateChanged, Transcript, Intent, ToolStarted/Finished, ApprovalRequested/Resolved, Reply, ModeChanged, PrivacyIndicator, Error, EchoHud, AudioLevel, TtsLevel. |
| `engine.ts` | Turn loop (LLM-first: chat → tool calls → compact results → follow-up), silent task plan with per-step evidence, completion guard, loop/budget/wall-time limits, deterministic `stop / pause / resume / task status`. |
| `policy.ts` | Path normaliser (`..`, UNC, device, ADS, 8.3, `%`, trailing dots), junction resolution hook, protected policy, tier escalation (never lowers), canonical SHA-256 call hash. |
| `approvals.ts` | Approvals bound to tool+args hash, T1 15 s / T2 30 s expiry, single-use, T2 click/hotkey only, voice rejected on loopback overlap, silence = deny. |
| `tools.ts` | ~45 tools in 12 packs + 4 hidden T3 tools. Zod arg schemas (unknown keys stripped, so a model-supplied `tier` is ignored), `{ok, evidence, data}` results with read-back. |
| `brain.ts` | Provider interface, scripted fake LLM (test double), optional Claude / Ollama adapters, router with hysteresis + mid-task failover. |
| `netguard.ts` | Offline guard (application level) + simulated link state + counters. |
| `redact.ts` | Secret redaction, markup stripping, `<<UNTRUSTED>>` wrapping. |
| `vpc.ts` | Postgres-backed virtual PC (windows, monitors, audio, files, Recycle Bin, junction). All tool tests run here, never on real folders. |
| `redteam.ts` | 25-case adversarial suite using the same engine. |

## Event flow for one turn
`Transcript → StateChanged(THINKING) → Intent → [ModeChanged] → (StateChanged(APPROVAL) → ApprovalRequested → ApprovalResolved)? → StateChanged(ACTING) → ToolStarted → ToolFinished → EchoHud? → … → Reply → (client) SPEAKING → IDLE`. Every event is persisted to `event_log` (levels excluded).

## Mapping to the spec's Windows architecture
| Spec | This build | Port path |
|---|---|---|
| Qt Quick notch | React + SVG, same geometry/palette tokens (`theme.ts`) | Re-implement `NotchShape/EdgeLight/…` in QML from `docs/UI_SPEC.md`; `useVox` reducer ≙ `NotchViewModel`. |
| Pydantic events | TS types in `events.ts` | 1:1 rename. |
| Wyzer `ToolRegistry` | `tools.ts` | Keep Wyzer's names; add `tier`, `pathArgs`, `preview`, `extraTier` hooks. |
| Isolated worker processes | single Node process (tools run on a sandbox) | Run each pack in a worker with timeouts. |
| Socket-level offline guard | `guardedFetch/netGate` | Patch `socket.connect`/DNS in core + workers. |
