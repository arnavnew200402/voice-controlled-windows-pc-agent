VOX GROQ VOICE — EARLY ACCESS

This is a real online push-to-talk voice slice, not the complete Windows agent.
It supports Notepad, Calculator, Paint and HTTPS websites only. Browser
navigation requires a click confirmation; other PC actions are not available.

1. Run VoxGroq.exe from the Start menu.
2. Paste your Groq API key into the application, not chat, and click Save key.
   It is encrypted using Windows DPAPI under %LOCALAPPDATA%\vox\groq.key.
3. Click Start recording, speak, then click Finish recording. Recording stops
   automatically after 15 seconds. Or type a request. Dry run is optional.
4. Review and approve any website before it opens. Stop is best-effort and
   cannot undo actions already started.

Groq receives the recording, transcript and text request; spoken replies also
use Groq. Voice services require network, model access and available quota, and
may incur charges. There is no continuous listening or screen capture. Voice,
live Groq, Windows apps, microphone and output have not been tested end to end.
To remove the key use Remove in the app; the uninstaller preserves user data.
Revoke compromised keys through the Groq console.

This unsigned early-access build may trigger Windows SmartScreen. Only install
it if you trust the source. It is not verified on a clean Windows VM. Review
licenses\THIRD_PARTY.md and NOTICE.md for third-party licensing.
