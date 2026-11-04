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


def play_wav(data: bytes) -> None:
    try:
        import winsound

        with wave.open(io.BytesIO(data), "rb") as audio:
            if not audio.getframerate() or audio.getnframes() / audio.getframerate() > 30:
                raise AudioError("Voice reply was invalid.")
        winsound.PlaySound(data, winsound.SND_MEMORY)  # type: ignore[attr-defined, unused-ignore]
    except AudioError:
        raise
    except Exception as exc:
        raise AudioError("Voice reply could not be played.") from exc
