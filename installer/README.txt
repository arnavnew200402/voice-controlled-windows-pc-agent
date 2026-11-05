VOX GROQ VOICE — EARLY ACCESS

This is a real online voice slice, not the complete Windows agent. It
supports built-in Windows apps, HTTPS websites, local folders, typing text,
scrolling, window control, file copy/move/delete, screenshots, clipboard
write and basic system information. Other PC actions are not available.

1. Run VoxGroq.exe from the Start menu.
2. Paste your Groq API key into the application, not chat, and click Save key.
   It is encrypted using Windows DPAPI under %LOCALAPPDATA%\vox\groq.key.
3. Turn on Hands-free, allow microphone access, then say "Hi Vox" followed
   by your request, e.g. "Hi Vox" ... "Open Notepad". Recording stops when
   you stop speaking. Or type a request instead. Dry run is optional.
4. Review and approve consequential actions (websites, folders, typing,
   window control, files, screenshots, clipboard) before they run. Stop is
   best-effort and cannot undo actions already started.

While Hands-free is on, the microphone is processed ONLY on this PC by a
bundled offline model that listens for "Hi Vox"; nothing is sent online
until the wake phrase is heard. Your request audio, transcript and text
requests are then sent to Groq; spoken replies also use Groq. Voice
services require network, model access and available quota, and may incur
charges. There is no screen capture except screenshots you explicitly
request and approve. Voice, live Groq, Windows apps, microphone and output
have not been tested end to end. To remove the key use Remove in the app;
the uninstaller preserves user data. Revoke compromised keys through the
Groq console.

This unsigned early-access build may trigger Windows SmartScreen. Only
install it if you trust the source. It is not verified on a clean Windows
VM. Review licenses\THIRD_PARTY.md and NOTICE.md for third-party licensing.
