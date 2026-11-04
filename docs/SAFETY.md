# Safety model (implemented in `src/lib/vox/policy.ts`, `approvals.ts`, `redact.ts`, `engine.ts`)

## Tiers
| Tier | Behaviour | Examples here |
|---|---|---|
| T0 Safe | runs immediately | open_app, move_window, set_volume, search_web, inspect_screen |
| T1 Confirm | approval card; voice or click | delete_path (Recycle Bin), move_file, rename, overwrite, empty_recycle_bin, set_default_audio_device, forget all, `win+r` |
| T2 Confirm-Hard | **click or Ctrl+Shift+Y only**; voice "yes" rejected server-side | shutdown/restart/sign_out, permanent_delete, non-allowlisted shell, bulk ≥100 items, `ctrl+alt+delete` |
| T3 Blocked | never runs, even if "approved"; audited | protected paths, UNC/device/ADS paths, credential stores, format/disable-defender/create-user tools, dangerous shell |

Tier is assigned by the tool, then **escalated, never lowered** by argument policy (`classify`). Zod strips unknown keys, so a model-supplied `tier`/`approved` argument is discarded (RT-15).

## Approvals
Bound to `sha256(tool + canonical(validated args))`; expire at 15 s (T1) / 30 s (T2); single-use; consumption re-checks tool, args and expiry right before execution (RT-12/13/14). "No", "cancel", "stop" and silence resolve to deny. Audit records `via = voice|click|hotkey|timeout|policy`.

## Path policy
`normalizePath` rejects: UNC, `\\.\`, `\\?\`, alternate data streams, device names (CON/NUL/COMn…), 8.3 short names, `%`, percent-encoded separators, NUL bytes, bad characters; resolves `..`, doubled separators, trailing dots/spaces; anchors relative paths at the profile root (never cwd). The engine also resolves junctions/symlinks to the real destination and classifies both. Deleting/moving an *ancestor* of a protected path is blocked too. The built-in protected set is not removable (user additions via `setUserProtected`).

## Untrusted content
Outputs of list_windows, inspect_screen, list_dir, read_text_file, read_page, search_web, get_clipboard, run_command, list_running are wrapped in `<<UNTRUSTED source=…>>`, stripped of role/tool markup, redacted (passwords, tokens, keys, cards, OTPs, private keys), and flagged when instruction-like. Once any untrusted output is in context, later T≥1 approval cards add "This came from page/file content." (first line, never truncated) and `remember` is refused.

## Known gaps (be honest)
- "Physical" confirmation in a browser is a trusted click/hotkey; the server cannot prove physicality.
- Voice-injection defence is a half-duplex gate + loopback-overlap flag, not real WASAPI loopback correlation.
- Offline guard is application-level, not socket-level.
- Rate limits on clicks/keystrokes are not implemented.
- Fuzzing covers path normalisation/classification (466 variants, 0 bypasses), not the Windows filesystem itself (reparse points, case-sensitivity flags, short-name generation).

## Red-team suite
`POST /api/redteam` (or Safety lab → Run suite). 25 cases, results saved to `artifacts/redteam.json` (25/25 on the production build). The "gullible" test model obeys instructions found in tool output, to prove the *system* — not the model's good behaviour — stops the attack.
