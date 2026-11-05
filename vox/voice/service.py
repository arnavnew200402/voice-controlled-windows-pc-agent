"""Real Groq voice pipeline shared by push-to-talk and hands-free capture.

The live engine (docs/LIVE_ENGINE_PLAN.md) is opt-in via engine.mode
(env ``VOX_ENGINE_MODE``, or the in-app toggle persisted under the vox
data directory); legacy single-shot planning stays the default until
the LE7 parity gate.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vox.agent.auth_storage import StorageError
from vox.agent.groq import GroqClient, HTTPSGroqTransport
from vox.agent.groq_key import windows_groq_store
from vox.agent.groq_tools import GroqRegistry, PlannedAction, WindowsDesktopBackend
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.approvals import Tier
from vox.voice.audio import AudioError, WinsoundPlayer, record_wav

if TYPE_CHECKING:
    from vox.engine.glossary import Glossary
    from vox.engine.pipeline import LivePipeline, TurnOutcome


def engine_data_dir() -> Path:
    """Where the persisted engine-mode flag lives."""
    override = os.environ.get("VOX_ENGINE_DIR")
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "vox" / ".vox"
    return Path.home() / ".vox"


@dataclass(frozen=True)
class Outcome:
    result: ToolResult | None = None
    pending: PlannedAction | None = None
    transcript: str = ""


class GroqVoiceService:
    def __init__(self) -> None:
        self.registry = GroqRegistry(WindowsDesktopBackend())
        self._pipeline: LivePipeline | None = None
        self._glossary: Glossary | None = None
        self._mode_override: str | None = None
        self._live_speaker: Callable[[str], None] = lambda _text: None

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
        return self.process_audio(wav, dry_run, cancelled, client=client)

    def process_audio(
        self,
        wav: bytes,
        dry_run: bool,
        cancelled: Callable[[], bool],
        *,
        client: GroqClient | None = None,
    ) -> Outcome:
        """Transcribe a captured request and run the same planning path as text."""
        client = client or self._client()
        transcript = client.transcribe(wav)
        if cancelled():
            raise ProviderError("Request cancelled before any action.")
        outcome = self.submit(transcript, dry_run, cancelled, client=client)
        return Outcome(result=outcome.result, pending=outcome.pending, transcript=transcript)

    def speak(self, text: str, cancelled: Callable[[], bool]) -> None:
        if not cancelled():
            audio = self._client().speech(text[:200])
            if not cancelled():
                # Cancellable playback: Stop silences speech within ~20 ms
                # instead of waiting for the whole utterance (LE1).
                player = WinsoundPlayer()
                player.play(audio, text[:200])
                player.wait(cancelled)

    # -- live engine (opt-in, LE4) ------------------------------------------

    def engine_mode(self) -> str:
        if self._mode_override is not None:
            return self._mode_override
        try:
            stored = (engine_data_dir() / "engine_mode.txt").read_text(encoding="utf-8")
        except OSError:
            stored = ""
        if stored.strip().lower() == "live":
            resolved = "live"
        elif stored.strip().lower() == "legacy":
            resolved = "legacy"
        else:
            from vox.engine.config import EngineMode, load_settings

            resolved = "live" if load_settings().mode is EngineMode.LIVE else "legacy"
        # The Qt property is polled through a broad change signal; resolve
        # the persisted/env default once per process instead of rereading it.
        self._mode_override = resolved
        return resolved

    def set_engine_mode(self, mode: str) -> str:
        normalised = "live" if mode.strip().lower() == "live" else "legacy"
        self._mode_override = normalised
        try:
            directory = engine_data_dir()
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "engine_mode.txt").write_text(normalised + "\n", encoding="utf-8")
        except OSError:
            pass  # in-memory override still applies this session
        return normalised

    def _live_pipeline(self, client: GroqClient | None = None) -> LivePipeline:
        if self._pipeline is None:
            from vox.engine.clock import SystemClock
            from vox.engine.context import CodeContextualiser, Contextualiser
            from vox.engine.entities import EntityRegistry
            from vox.engine.glossary import Glossary
            from vox.engine.ledger import ActionsLedger
            from vox.engine.memory import PreferencesSheet, UserCard
            from vox.engine.pipeline import LivePipeline
            from vox.engine.timeline import Timeline
            from vox.engine.turns import TurnManager

            clock = SystemClock()
            timeline = Timeline(clock)
            entities = EntityRegistry(clock)
            self._glossary = Glossary()
            self._pipeline = LivePipeline(
                registry=self.registry,
                client=client or self._client(),
                timeline=timeline,
                manager=TurnManager(timeline, clock),
                contextualiser=Contextualiser(CodeContextualiser(entities, self._glossary)),
                entities=entities,
                glossary=self._glossary,
                ledger=ActionsLedger(clock),
                user_card=UserCard.load(),
                preferences=PreferencesSheet.load(),
                clock=clock,
                speaker=lambda sentence: self._live_speaker(sentence),
            )
        else:
            # Refresh credentials so key changes apply without a restart.
            self._pipeline.set_client(client or self._client())
        return self._pipeline

    def _speak_live_sentence(self, sentence: str, cancelled: Callable[[], bool]) -> None:
        """Best-effort sentence playback.

        A TTS/player failure must not abort a live turn or obscure an
        action that has already completed; the text outcome still reaches
        the UI, matching the legacy worker's speech-failure handling.
        """
        try:
            self.speak(sentence, cancelled)
        except (ProviderError, AudioError, StorageError):
            return

    def live_submit(
        self,
        text: str,
        dry_run: bool,
        cancelled: Callable[[], bool],
        *,
        speak: bool = True,
    ) -> TurnOutcome:
        if not text.strip() or len(text) > 4000:
            raise ProviderError("Enter a request of up to 4,000 characters.")
        if cancelled():
            raise ProviderError("Request cancelled.")
        pipeline = self._live_pipeline()
        self._live_speaker = (
            (lambda sentence: self._speak_live_sentence(sentence, cancelled))
            if speak
            else (lambda _sentence: None)
        )
        return pipeline.run_turn(text, trigger="typed", dry_run=dry_run)

    def live_process_audio(
        self,
        wav: bytes,
        dry_run: bool,
        cancelled: Callable[[], bool],
        *,
        client: GroqClient | None = None,
        speak: bool = True,
    ) -> TurnOutcome:
        client = client or self._client()
        pipeline = self._live_pipeline(client)
        assert self._glossary is not None
        hotwords = self._glossary.hotwords()
        transcript = client.transcribe_detailed(wav, prompt=hotwords or None)
        if not transcript.text.strip():
            raise ProviderError("No speech was recognised.")
        if cancelled():
            raise ProviderError("Request cancelled before any action.")
        self._live_speaker = (
            (lambda sentence: self._speak_live_sentence(sentence, cancelled))
            if speak
            else (lambda _sentence: None)
        )
        return pipeline.run_turn(
            transcript.text,
            trigger="voice",
            asr_confidence=transcript.confidence,
            dry_run=dry_run,
        )

    def live_approve(self, approved: bool) -> TurnOutcome | None:
        if self._pipeline is None:
            return None
        return self._pipeline.approve_pending(approved)

    def live_deny(self) -> TurnOutcome | None:
        """Synchronous, silent denial for UI-thread deny/cancel paths."""
        if self._pipeline is None:
            return None
        previous = self._live_speaker
        self._live_speaker = lambda _sentence: None
        try:
            return self._pipeline.approve_pending(False)
        finally:
            self._live_speaker = previous

    def live_rebind_pending(self, action: PlannedAction) -> bool:
        if self._pipeline is None:
            return False
        return self._pipeline.rebind_pending(action)

    def live_history_lines(self, limit: int = 8) -> list[str]:
        if self._pipeline is None:
            return []
        from vox.engine.prompt_assembly import recent_turns_text

        text = recent_turns_text(self._pipeline.timeline)
        return [line for line in text.splitlines() if line.strip()][-limit:]
