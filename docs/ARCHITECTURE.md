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

## Native foundation (work in progress, separate from web reference)

`python -m vox` without options reports the available experimental paths. `--text` can invoke the ChatGPT provider (or explicitly selected local provider) and a narrowly restricted Windows Notepad launcher; `--ui-demo` remains a sandbox. `vox/approvals.py` supplies a thread-safe, in-memory approval primitive inspired by Wyzer's binding and the reference design. It accepts Pydantic model instances, hashes the canonical JSON representation along with the tool name, uses monotonic deadlines, and binds consumption to the effective tier. A stop revokes pending and approved-but-not-yet-consumed requests. The store has a bounded capacity; terminal entries may be discarded under pressure, so they must be persisted to the future audit ledger before relying on this for production. This is independent new code, not a port of Wyzer. The Python and TypeScript implementations are not yet integrated.

**Integration prerequisites:** the future registry must validate and freeze/revalidate tool arguments before both request and execution, calculate and recheck escalation from trusted policy, establish input provenance outside model/network control, and coordinate cancellation with execution (revocation cannot undo a consumed action). Voice approval requires real loopback verification; the current boolean is only a trusted adapter assertion and is not that verification. T2 click/hotkey provenance is likewise not proven by this primitive. No native production policy enforcement, audit logging, event bus, isolated workers, real tools, or offline guarantee is in place. Do not wire this module to consequential actions until those boundaries are implemented and tested.

## Native UI design studio

`python -m vox --ui-demo` loads PySide6/Qt Quick files under `vox/ui/qml/` with a presentation-only `NotchDemoModel`. A separate studio chooses ten synthetic states; the top-edge preview is non-activating and entirely transparent to input, including the fake approval buttons. A connected sandbox walkthrough uses a dedicated Python thread, `queue.Queue` and versioned Pydantic events to update the view model on the Qt thread. It uses the in-memory `ApprovalStore` only for simulated virtual file deletion; approval decisions are made in the studio, not the notch. The two scripted scenarios modify only in-memory demo state. This is not connected to the actual agent core, real tools, model providers, or audio. Placement uses the primary screen's available geometry and updates on that screen's work-area changes. The work-area placement, click-through and focus behavior must still be tested on Windows; screen replacement, fullscreen, DPI changes, tray, real hover/input, privacy and event-bus integration remain unimplemented.

### Sandbox integration boundary

`vox/demo/engine.py` implements two fixed scenarios, not intent routing: an in-memory app list and an in-memory Downloads list. Deletion snapshots the complete virtual file tuple in frozen validated arguments, requests T1 approval, rechecks the snapshot and consumes the binding before changing the list. `vox/demo/worker.py` drives this state machine off the UI thread and transports typed events by queue; a Qt timer applies them in the UI thread. Stop revokes pending/approved sandbox requests. The worker is a thread, not an isolated process, and the event queue is not a persisted ledger. It is **not** a production security boundary or a way to execute Windows actions; click provenance, real reparse points, redaction, policy, audit and cross-process cancellation still need implementation.

## Experimental local text vertical slice

`python -m vox --provider ollama --text ... --model ...` connects `OllamaProvider` → `ToolRegistry` → `WindowsNotepadBackend`. The Ollama HTTP transport is hard-coded to numeric loopback, uses no proxies or redirects and limits response size; this is not a process-wide socket guard. The only registered schema is strict `open_app(name=Notepad)`; extra arguments, unknown tools, and multiple tool calls are rejected before execution. The Windows backend launches the fixed `notepad.exe` in the OS-reported system directory without a shell and checks process liveness and foreground PID. `--dry-run` substitutes a fake backend. The user sees evidence, not free-form model claims. Tests use fakes and a recorded local loopback server. The path is not wired to the Qt notch, audit ledger, stop handler or voice pipeline, and it does not have worker isolation, multi-step plans, online fallback, production policy or a live model acceptance benchmark. Actual Windows behavior has not been tested; a delegated/reused Notepad process may cause a conservative verification failure. No unsafe or consequential tools are registered.

## Experimental ChatGPT online provider

`--login` starts the documented SIWC dynamic registration OAuth flow using system browser, loopback callback, state, nonce and PKCE S256. ID tokens are checked against OpenAI JWKS for RS256 signature, issuer, audience, expiration and nonce; the required ChatGPT plan scopes are checked. A validated single-account record is stored with Windows DPAPI in `%LOCALAPPDATA%/vox/chatgpt.dat` (atomic replacement); no keys or tokens are put in the repository. `--text` defaults to `ChatGPTProvider`, sends the text and closed `open_app` schema to the official Responses endpoint, and executes only a single validated tool call after `response.completed`. Requests use `stream=true`, `store=false` and a namespaced tool as required by the current ChatGPT-plan preview. Model is explicit or first visible result from the account model catalog. `--provider ollama` remains separately available.

Limitations: no live OAuth, provider, DPAPI or Windows desktop test has run; the Linux tests use fake credentials, generated signing keys, recorded SSE and a loopback callback. One saved account only; refresh tokens are stored but **not refreshed**, so the user must reauthenticate when expired. There is no sign-out/revocation flow or UI connection, no safe cross-process refresh serialization, and no live error-code/usage recovery. The provider sends user text to OpenAI and is not an offline mode. Notepad is still the only real tool, and the tool path is not isolated or cancellable. Sources: https://developers.openai.com/siwc/token-sharing-open-source/sign-in and https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations.
