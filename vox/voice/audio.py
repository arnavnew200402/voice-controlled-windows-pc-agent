"""Microphone capture and Windows playback helpers for push-to-talk and hands-free.

Policy lives in the callers: this module only moves bounded PCM frames between
the default microphone/speakers and memory. Nothing is written to disk.
"""

from __future__ import annotations

import io
import math
import struct
import time
import wave
from collections.abc import Callable, Iterator
from contextlib import suppress
from typing import Any

SAMPLE_RATE = 16000
FRAME_SAMPLES = 4000  # 0.25 s of mono audio per frame


class AudioError(RuntimeError):
    pass


class NoSpeechError(AudioError):
    """Capture finished without anything loud enough to be a request."""


def frame_rms(frame: bytes) -> float:
    """RMS level of little-endian int16 PCM, normalized to 0..1."""
    count = len(frame) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", frame[: count * 2])
    return math.sqrt(sum(s * s for s in samples) / count) / 32768.0


def _wav_bytes(chunks: list[bytes]) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(b"".join(chunks))
    return output.getvalue()


def record_wav(
    finished: Callable[[], bool], cancelled: Callable[[], bool], *, max_seconds: float = 15.0
) -> bytes:
    try:
        import sounddevice as sd  # type: ignore[import-untyped]

        chunks: list[bytes] = []
        deadline = time.monotonic() + max_seconds
        with sd.RawInputStream(
            samplerate=16000, channels=1, dtype="int16", blocksize=1600
        ) as stream:
            while not finished() and not cancelled() and time.monotonic() < deadline:
                data, _overflowed = stream.read(1600)
                chunks.append(bytes(data))
        if cancelled():
            raise AudioError("Recording cancelled.")
        if not chunks:
            raise AudioError("No audio was recorded.")
        return _wav_bytes(chunks)
    except AudioError:
        raise
    except Exception as exc:
        raise AudioError("Microphone unavailable. Check Windows microphone permissions.") from exc


def iter_microphone_frames(
    cancelled: Callable[[], bool], *, frame_samples: int = FRAME_SAMPLES
) -> Iterator[bytes]:
    """Yield raw PCM frames from the default microphone until cancelled.

    The caller owns policy (wake-word spotting, endpointing, retention). Any
    device error is reported as AudioError instead of leaking backend detail.
    """
    try:
        import sounddevice as sd  # already imported (with ignore) in record_wav

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frame_samples
        ) as stream:
            while not cancelled():
                data, _overflowed = stream.read(frame_samples)
                yield bytes(data)
    except AudioError:
        raise
    except Exception as exc:
        raise AudioError("Microphone unavailable. Check Windows microphone permissions.") from exc


def record_until_silence(
    cancelled: Callable[[], bool],
    *,
    max_seconds: float = 15.0,
    no_speech_seconds: float = 6.0,
    silence_seconds: float = 1.1,
    threshold: float = 0.03,
) -> bytes:
    """Record one spoken request, ending shortly after the speaker stops.

    Energy-based endpointing only; no transcription happens here. Raises
    NoSpeechError when nothing above the threshold is heard in time.
    """
    frame_seconds = FRAME_SAMPLES / SAMPLE_RATE
    silence_frames_needed = max(1, round(silence_seconds / frame_seconds))
    chunks: list[bytes] = []
    heard_speech = False
    trailing_silence = 0
    deadline = time.monotonic() + max_seconds
    speech_deadline = time.monotonic() + no_speech_seconds
    for frame in iter_microphone_frames(cancelled):
        chunks.append(frame)
        if frame_rms(frame) >= threshold:
            heard_speech = True
            trailing_silence = 0
        elif heard_speech:
            trailing_silence += 1
            if trailing_silence >= silence_frames_needed:
                break
        now = time.monotonic()
        if now >= deadline:
            break
        if not heard_speech and now >= speech_deadline:
            break
    if cancelled():
        raise AudioError("Recording cancelled.")
    if not heard_speech:
        raise NoSpeechError("I didn't hear a request.")
    return _wav_bytes(chunks)


def _wav_duration_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as audio:
        rate = audio.getframerate()
        if not rate:
            raise AudioError("Voice reply was invalid.")
        duration = audio.getnframes() / rate
    if duration > 30:
        raise AudioError("Voice reply was invalid.")
    return duration


class WinsoundPlayer:
    """Cancellable WAV playback (LE1) with a spoken-text estimate.

    ``play`` starts async ``winsound`` playback; ``stop`` silences it
    immediately and returns the portion of ``text`` estimated spoken from
    elapsed time (word-boundary trimmed). ``wait`` blocks until the sound
    ends or ``cancelled`` fires, polling every 20 ms so cancellation lands
    well inside the 150 ms budget. Non-Windows platforms raise
    ``AudioError`` exactly like the legacy blocking helper.
    """

    def __init__(self) -> None:
        self._started: float | None = None
        self._duration = 0.0
        self._text = ""
        self._data = b""  # SND_MEMORY|SND_ASYNC requires a live buffer
        self._winsound: Any = None

    @property
    def playing(self) -> bool:
        return self._started is not None

    def play(self, data: bytes, text: str = "") -> None:
        try:
            import winsound

            duration = _wav_duration_seconds(data)
            winsound.PlaySound(  # type: ignore[attr-defined, unused-ignore]
                data,
                winsound.SND_MEMORY | winsound.SND_ASYNC,  # type: ignore[attr-defined, unused-ignore]
            )
        except AudioError:
            raise
        except Exception as exc:
            raise AudioError("Voice reply could not be played.") from exc
        self._winsound = winsound
        self._data = data
        self._text = text
        self._duration = duration
        self._started = time.monotonic()

    def stop(self) -> str:
        if not self.playing:
            return ""
        spoken = self._spoken_estimate()
        with suppress(Exception):  # already silent is fine during shutdown
            self._winsound.PlaySound(None, self._winsound.SND_PURGE)  # type: ignore[attr-defined, unused-ignore]
        self._reset()
        return spoken

    def wait(self, cancelled: Callable[[], bool] | None = None) -> str:
        if not self.playing or self._started is None:
            return ""
        while time.monotonic() - self._started < self._duration:
            if cancelled is not None and cancelled():
                return self.stop()
            time.sleep(0.02)
        spoken = self._text
        self._reset()
        return spoken

    def _spoken_estimate(self) -> str:
        if self._started is None or self._duration <= 0 or not self._text:
            return "" if self._started is None else self._text
        ratio = min(1.0, max(0.0, (time.monotonic() - self._started) / self._duration))
        cut = int(len(self._text) * ratio)
        spoken = self._text[:cut]
        if 0 < cut < len(self._text) and " " in spoken:
            spoken = spoken.rsplit(" ", 1)[0]
        return spoken

    def _reset(self) -> None:
        self._started = None
        self._data = b""
        self._text = ""
        self._duration = 0.0


def play_wav(data: bytes) -> None:
    """Legacy blocking playback (unchanged semantics for the legacy path)."""
    player = WinsoundPlayer()
    player.play(data)
    player.wait()
