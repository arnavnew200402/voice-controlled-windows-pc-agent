# Windows physical validation checklist

Everything in CI is green with **fakes and offscreen rendering**. The checks below
have never run on a real Windows desktop, microphone, or Groq account. They are
the remaining gate for calling the current Groq early-access slice "verified".
Any failure is a real bug report: note the exact status text the app shows.

Safety first: use a disposable Windows 10/11 VM or a secondary Windows account,
a scratch folder (e.g. `C:\VoxTest`) for file tests, and clear sensitive windows
before the screenshot step. Use your own Groq API key; never share it in issues.

## 0. Get the installer
- [ ] Open the repo **Actions** tab → latest **“Windows preview installer”** run
  on branch `arena/32bc43fd-voice-controlled-windows-pc-ag` with a green check
  → download artifact `vox-windows-groq-early-access` and unzip it.
- [ ] Confirm the artifact came from a commit you expect (run page shows the SHA).

## 1. Install / launch
- [ ] Run the installer. It is unsigned, so SmartScreen may warn
  (*More info → Run anyway*). Note any other error verbatim.
- [ ] App appears in the Start menu and launches without missing-DLL or
  Python errors; the notch/control UI renders at your display scaling.
- [ ] Dry-run is easy to find; microphone is **not** active until you press
  push-to-talk.

## 2. Groq key (DPAPI)
- [ ] Paste your Groq API key and save. Status confirms DPAPI save.
- [ ] Restart the app: key is still present (no re-entry needed).
- [ ] Remove the key; restart: app asks for a key again. Re-save it for below.
- [ ] Enter a deliberately wrong key: you get a clear error, no crash, and the
  bad key is not echoed anywhere.

## 3. Voice loop (live Groq)
- [ ] Push-to-talk: Windows microphone permission prompt appears the first
  time; deny it once and confirm a clear error, then allow it.
- [ ] Say “Open Calculator”, finish recording. Transcript shown matches speech;
  Calculator opens. Recording indicator was visible only while recording.
- [ ] Enable spoken replies: the result is spoken through your speakers
  (Orpheus TTS) and matches the on-screen evidence.
- [ ] Say something unsupported (e.g. “restart the PC”): clear refusal,
  nothing happens on the desktop.
- [ ] Type a request instead of speaking; same behavior. Dry-run a request:
  it reports what *would* happen and does nothing.

## 4. Actions (each consequential one must show an approval first)
For every item: the approval card must show the **exact** argument (URL, path,
text) before anything happens; declining must do nothing; approval must not be
reusable (acting again requires a new approval).

- [ ] Open Notepad, Paint, Settings, File Explorer, Browser (one by one).
- [ ] “Open https://example.com” → approval shows the URL → browser opens it.
  Try an `http://` or local/IP address → rejected before approval.
- [ ] “Open my Downloads folder” → approval shows the resolved real path →
  Explorer opens there.
- [ ] Typing: open Notepad, click into it, request typing a short sentence.
  The window picker lists real visible windows with correct titles; text
  lands **only** in the window you selected. Switch focus after selecting
  but before approving → action should refuse rather than type elsewhere.
- [ ] Scroll/minimize/maximize/restore/close act on the selected window only.
- [ ] File ops inside `C:\VoxTest` only: copy `a.txt`→`b.txt`, move
  `b.txt`→`c.txt`, delete `c.txt`; verify in Explorer. A path outside the
  scratch folder that you decline remains untouched.
- [ ] Screenshot to `C:\VoxTest\shot.bmp`: the file opens as a real image of
  the screen at that moment (check resolution/content, then delete it).
- [ ] “Copy *<some text>* to clipboard”: approval shows the exact text;
  afterwards paste (Ctrl+V) into Notepad shows exactly that text.
- [ ] “System info”: plausible Windows version/architecture/disk numbers;
  no user or machine name appears.

## 5. Stop / expiry
- [ ] Start a request, press Stop mid-way: recording/network stops; nothing
  was executed (or an already-started action is reported honestly).
- [ ] Leave an approval card untouched ~20 s: approving afterwards fails as
  expired and nothing executes.

## 6. Uninstall
- [ ] Uninstall from Settings → Apps. Start-menu entry and program files gone.
- [ ] Saved Groq key: remove it from inside the app **before** uninstall, and
  note anything left behind under your user profile for the bug report.

## Results
| Section | Pass/Fail | Notes (exact status text, Windows version, scaling) |
| --- | --- | --- |
| 1 Install/launch |  |  |
| 2 Key/DPAPI |  |  |
| 3 Voice loop |  |  |
| 4 Actions |  |  |
| 5 Stop/expiry |  |  |
| 6 Uninstall |  |  |

Still out of scope for this checklist (future backlog, not this slice):
wake word/continuous listening, speaker verification, offline mode, code
signing, and any tool not in the closed registry listed in `STATE.md`.
