VOX EARLY WINDOWS PREVIEW

This is not the complete voice-controlled Windows agent. It has a ChatGPT
sign-in and a limited text request path for opening Windows Notepad only.
Dry run is enabled by default. Voice, general PC control, offline mode,
production approvals, and the full safety model are not included.

1. Run VoxPreview.exe from the Start menu after installation.
2. Use Continue with ChatGPT and approve the sign-in in your browser.
3. Try "Open Notepad" with Dry run checked first. To try a real launch,
   uncheck Dry run. Only Notepad is available.

OpenAI ChatGPT plan eligibility and service availability apply. Real
OAuth and Notepad functionality may vary by account and Windows version.
The app sends your request text to OpenAI. Tokens are protected by Windows
DPAPI under %LOCALAPPDATA%\vox. The uninstaller leaves that user data in
place. Token refresh and app-side revocation are not implemented; sign in
again when the session expires, and disconnect the app in ChatGPT settings
to revoke access. Stopping is best-effort; an action already started cannot
be undone.

This preview is unsigned and may trigger Windows SmartScreen. Only install
it if you trust its source. It has not been verified on a clean Windows VM.
See licenses\THIRD_PARTY.md and NOTICE.md for third-party licensing.
