"""Real Groq push-to-talk pipeline; no Qt or continuous microphone capture."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vox.agent.groq import GroqClient, HTTPSGroqTransport
from vox.agent.groq_key import windows_groq_store
from vox.agent.groq_tools import GroqRegistry, PlannedAction, WindowsDesktopBackend
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.approvals import Tier
from vox.voice.audio import play_wav, record_wav


@dataclass(frozen=True)
class Outcome:
    result: ToolResult | None = None
    pending: PlannedAction | None = None
    transcript: str = ""


class GroqVoiceService:
    def __init__(self) -> None:
        self.registry = GroqRegistry(WindowsDesktopBackend())

    def save_key(self, key: str) -> None:
        windows_groq_store().save(key)

    def delete_key(self) -> None:
        windows_groq_store().delete()

    def _client(self) -> GroqClient:
        return GroqClient(HTTPSGroqTransport(windows_groq_store().load()))

    def submit(
        self,
        text: str,
        dry_run: bool,
        cancelled: Callable[[], bool],
        *,
        client: GroqClient | None = None,
    ) -> Outcome:
        if not text.strip() or len(text) > 4000:
            raise ProviderError("Enter a request of up to 4,000 characters.")
        if cancelled():
            raise ProviderError("Request cancelled.")
        client = client or self._client()
        message = client.chat(text, self.registry.schemas())
        if cancelled():
            raise ProviderError("Request cancelled before any action.")
        action = self.registry.plan(message)
        if dry_run:
            return Outcome(
                result=ToolResult(
                    ok=True,
                    simulated=True,
                    evidence="Dry run: " + action.description + " No action was performed.",
                )
            )
        if action.tier == Tier.CONFIRM:
            return Outcome(pending=action)
        if cancelled():
            raise ProviderError("Request cancelled before any action.")
        return Outcome(result=self.registry.execute(action))

    def voice(
        self,
        finished: Callable[[], bool],
        cancelled: Callable[[], bool],
        dry_run: bool,
        on_processing: Callable[[], None],
    ) -> Outcome:
        # Load the key before recording so a missing key never activates the microphone.
        client = self._client()
        wav = record_wav(finished, cancelled)
        if cancelled():
            raise ProviderError("Recording cancelled.")
        on_processing()
        transcript = client.transcribe(wav)
        if cancelled():
            raise ProviderError("Request cancelled before any action.")
        outcome = self.submit(transcript, dry_run, cancelled, client=client)
        return Outcome(result=outcome.result, pending=outcome.pending, transcript=transcript)

    def speak(self, text: str, cancelled: Callable[[], bool]) -> None:
        if not cancelled():
            audio = self._client().speech(text[:200])
            if not cancelled():
                play_wav(audio)
