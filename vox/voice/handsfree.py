"""Hands-free loop: local wake phrase, one request, spoken result, repeat.

The controller owns sequencing only. Microphone frames, wake spotting,
request capture, Groq processing and speech playback are injected callables,
so the full loop is testable with fakes and no audio device. The microphone
phases never overlap playback: the frame iterator finishes before a request
is captured, and capture finishes before anything is processed or spoken.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable

from vox.agent.auth_storage import StorageError
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.voice.audio import AudioError, NoSpeechError
from vox.voice.service import Outcome
from vox.voice.wake import WakeEngine, WakeError

Cancelled = Callable[[], bool]
FrameSource = Callable[[Cancelled], Iterable[bytes]]
CaptureCommand = Callable[[Cancelled], bytes]
ProcessAudio = Callable[[bytes, bool, Cancelled], Outcome]
SpeakResult = Callable[[str, Cancelled], None]


class HandsFreeController:
    def __init__(
        self,
        *,
        engine_factory: Callable[[], WakeEngine],
        frame_source: FrameSource,
        capture_command: CaptureCommand,
        process_audio: ProcessAudio,
        speak_result: SpeakResult,
        on_state: Callable[[str], None],
        on_outcome: Callable[[Outcome], None],
        on_error: Callable[[str], None],
        pause_after_speak: float = 0.4,
    ) -> None:
        self._engine_factory = engine_factory
        self._frame_source = frame_source
        self._capture_command = capture_command
        self._process_audio = process_audio
        self._speak_result = speak_result
        self._on_state = on_state
        self._on_outcome = on_outcome
        self._on_error = on_error
        self._pause_after_speak = pause_after_speak
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, *, dry_run: bool, speak: bool) -> None:
        if self.running:
            return
        self._cancel.clear()
        self._resume.set()
        self._thread = threading.Thread(
            target=self._run, args=(dry_run, speak), name="vox-handsfree", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._cancel.set()
        self._resume.set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def _run(self, dry_run: bool, speak: bool) -> None:
        cancelled = self._cancel.is_set
        try:
            self._on_state("starting")
            engine = self._engine_factory()
            while not cancelled():
                self._on_state("wake")
                if not self._wait_for_wake(engine, cancelled):
                    break
                if cancelled():
                    break
                self._on_state("command")
                try:
                    wav = self._capture_command(cancelled)
                except NoSpeechError:
                    continue  # Heard the wake phrase but no request followed.
                except AudioError as exc:
                    self._on_error(str(exc))
                    continue
                self._on_state("processing")
                try:
                    outcome = self._process_audio(wav, dry_run, cancelled)
                    if outcome.result is not None and speak and not cancelled():
                        outcome = self._speak(outcome, cancelled)
                except (AudioError, ProviderError, StorageError) as exc:
                    # A misheard request or provider hiccup ends this turn,
                    # not the whole hands-free session.
                    if cancelled():
                        break
                    self._on_error(str(exc))
                    continue
                if cancelled():
                    break
                self._on_outcome(outcome)
                if outcome.pending is not None:
                    # Consequential actions still need the click-approval card;
                    # wake listening stays paused until the UI resolves it.
                    self._resume.clear()
        except WakeError as exc:
            self._on_error(str(exc))
        except (AudioError, ProviderError, StorageError) as exc:
            if not cancelled():
                self._on_error(str(exc))
        except Exception:  # noqa: BLE001 - a background loop must report, not crash the UI
            if not cancelled():
                self._on_error("Hands-free listening stopped unexpectedly.")
        finally:
            self._on_state("off")

    def _wait_for_wake(self, engine: WakeEngine, cancelled: Cancelled) -> bool:
        for frame in self._frame_source(cancelled):
            if cancelled():
                return False
            if not self._resume.is_set():
                # Paused for an approval card: discard frames without feeding
                # the spotter so the wake phrase cannot queue a second request.
                self._resume.wait(timeout=0.05)
                continue
            if engine.feed(frame):
                return True
        return False

    def _speak(self, outcome: Outcome, cancelled: Cancelled) -> Outcome:
        assert outcome.result is not None
        self._on_state("speaking")
        try:
            self._speak_result(outcome.result.evidence, cancelled)
        except Exception:  # noqa: BLE001 - preserve the completed action's evidence
            outcome = Outcome(
                result=ToolResult(
                    ok=outcome.result.ok,
                    simulated=outcome.result.simulated,
                    evidence=outcome.result.evidence + " Voice reply unavailable.",
                ),
                transcript=outcome.transcript,
            )
        if self._pause_after_speak > 0:
            # Let the room go quiet so the tail of our own voice reply is not
            # treated as conversation by the next wake-listen pass.
            time.sleep(self._pause_after_speak)
        return outcome
