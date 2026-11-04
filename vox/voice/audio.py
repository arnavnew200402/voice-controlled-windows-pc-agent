"""Push-to-talk capture and Windows playback. No continuous listening."""

from __future__ import annotations

import io
import time
import wave
from collections.abc import Callable


class AudioError(RuntimeError):
    pass


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
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"".join(chunks))
        return output.getvalue()
    except AudioError:
        raise
    except Exception as exc:
        raise AudioError("Microphone unavailable. Check Windows microphone permissions.") from exc


def play_wav(data: bytes) -> None:
    try:
        import winsound

        with wave.open(io.BytesIO(data), "rb") as audio:
            if not audio.getframerate() or audio.getnframes() / audio.getframerate() > 30:
                raise AudioError("Voice reply was invalid.")
        winsound.PlaySound(data, winsound.SND_MEMORY)  # type: ignore[attr-defined]
    except AudioError:
        raise
    except Exception as exc:
        raise AudioError("Voice reply could not be played.") from exc
