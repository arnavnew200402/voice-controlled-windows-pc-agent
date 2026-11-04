"""On-device wake-phrase spotting. No audio leaves the PC in this module.

A small offline Vosk recognizer runs over microphone frames and only reports
whether a wake phrase ("Hi Vox" and common mis-hearings such as "hey box")
was spoken. Snippets are never sent online; they may be shown locally in the
UI ("Heard locally") purely so users can diagnose microphone problems. The
request itself is captured separately and sent to Groq by the caller.

The speech model (~40 MB, Apache-2.0) is bundled with the installer when
available; otherwise it is downloaded once, on first hands-free enable, into
the per-user app data folder.
"""

from __future__ import annotations

import importlib
import io
import itertools
import json
import os
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MAX_MODEL_BYTES = 100 * 1024 * 1024

# Canonical phrases. "Vox" is out-of-vocabulary for small English models, so
# the matcher below also accepts the words recognizers commonly substitute
# for it — but only when paired with a greeting, so ordinary sentences such
# as "a box" or "I walks" never wake the assistant.
WAKE_PHRASES = (
    "hi vox",
    "hey vox",
    "okay vox",
    "ok vox",
    "hi box",
    "hey box",
    "hi fox",
    "hey fox",
)

_STRONG_GREETINGS = {"hi", "hey", "ok", "okay"}
_WEAK_GREETINGS = {"high", "hay", "he", "i"}  # plausible mis-hearings of "hi"
_NAME_VARIANTS = {
    "vox",
    "box",
    "fox",
    "walks",
    "wax",
    "vax",
    "vaux",
    "valk",
    "volks",
    "voss",
    "vos",
}
_MERGED = {"hivox", "heyvox", "okvox", "okayvox"}


class WakeError(RuntimeError):
    pass


class WakeEngine(Protocol):
    def feed(self, frame: bytes) -> bool: ...


def _tokens(text: str) -> list[str]:
    return "".join(char.lower() if char.isalnum() else " " for char in text).split()


def contains_wake_phrase(text: str) -> bool:
    """True when a recognized snippet contains a wake phrase as whole words."""
    tokens = _tokens(text)
    if any(token in _MERGED for token in tokens):
        return True
    for greeting, name in itertools.pairwise(tokens):
        if greeting in _STRONG_GREETINGS and name in _NAME_VARIANTS:
            return True
        if greeting in _WEAK_GREETINGS and name == "vox":
            return True
    return False


def _model_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle_root, str):
        candidates.append(Path(bundle_root) / "vox" / "wake-model" / MODEL_NAME)
    candidates.append(Path(__file__).resolve().parent / "wake-model" / MODEL_NAME)
    return candidates


def cached_model_path() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "vox" / "wake-model" / MODEL_NAME
    return Path.home() / ".local" / "share" / "vox" / "wake-model" / MODEL_NAME


def _looks_like_model(path: Path) -> bool:
    return path.is_dir() and (path / "am").is_dir() and (path / "conf").is_dir()


def find_model() -> Path | None:
    for candidate in [*_model_root_candidates(), cached_model_path()]:
        if _looks_like_model(candidate):
            return candidate
    return None


def _download_model(target: Path, *, opener: Any = None) -> None:
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(MODEL_URL, timeout=60) as response:
            data = response.read(MAX_MODEL_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise WakeError("Could not download the offline wake-word model.") from exc
    if len(data) > MAX_MODEL_BYTES:
        raise WakeError("The wake-word model download was unexpectedly large.")
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{MODEL_NAME}.staging"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                # Renaming after extraction below expects one top-level folder.
                destination = (staging / member.filename).resolve()
                if not destination.is_relative_to(staging.resolve()):
                    raise WakeError("The wake-word model archive was invalid.")
                archive.extract(member, staging)
        extracted = staging / MODEL_NAME
        if not _looks_like_model(extracted):
            raise WakeError("The wake-word model archive was invalid.")
        if target.exists():
            raise WakeError("The wake-word model is already installed but unreadable.")
        extracted.rename(target)
    except WakeError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise WakeError("Could not install the offline wake-word model.") from exc
    finally:
        # Best-effort staging cleanup; never mask the real error.
        try:
            for leftover in sorted(staging.rglob("*"), reverse=True):
                if leftover.is_file():
                    leftover.unlink()
                else:
                    leftover.rmdir()
            staging.rmdir()
        except OSError:
            pass


def ensure_model() -> Path:
    """Return a usable model path, downloading it once if necessary."""
    found = find_model()
    if found is not None:
        return found
    target = cached_model_path()
    _download_model(target)
    if not _looks_like_model(target):
        raise WakeError("The wake-word model could not be prepared.")
    return target


class VoskWakeEngine:
    """Streaming wake-phrase spotter over 16 kHz mono int16 frames."""

    def __init__(self, model_path: Path | None = None) -> None:
        try:
            vosk = importlib.import_module("vosk")
        except ImportError as exc:
            raise WakeError(
                "Hands-free support is not installed. Reinstall Vox or install the voice extras."
            ) from exc
        vosk.SetLogLevel(-1)
        path = model_path or ensure_model()
        try:
            model = vosk.Model(str(path))
            self._recognizer = vosk.KaldiRecognizer(model, 16000)
        except (OSError, RuntimeError, ValueError) as exc:
            raise WakeError("The wake-word model could not be loaded.") from exc
        self._recognizer.SetWords(False)
        self._on_heard: Callable[[str], None] | None = None
        self._last_heard = ""

    def set_on_heard(self, callback: Callable[[str], None]) -> None:
        """Register a diagnostic sink for locally recognized snippets.

        The callback receives partial/final wake-spotter text (never sent
        online) so the UI can show what the microphone path actually hears.
        """
        self._on_heard = callback

    def _emit_heard(self, text: str) -> None:
        cleaned = " ".join(text.split())
        if cleaned and cleaned != self._last_heard:
            self._last_heard = cleaned
            if self._on_heard is not None:
                self._on_heard(cleaned)

    def feed(self, frame: bytes) -> bool:
        if self._recognizer.AcceptWaveform(frame):
            text = self._snippet(self._recognizer.Result(), "text")
            self._emit_heard(text)
            if contains_wake_phrase(text):
                self._recognizer.Reset()
                return True
            return False
        partial = self._snippet(self._recognizer.PartialResult(), "partial")
        self._emit_heard(partial)
        if contains_wake_phrase(partial):
            self._recognizer.Reset()
            return True
        return False

    @staticmethod
    def _snippet(payload: Any, key: str) -> str:
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return ""
        value = parsed.get(key) if isinstance(parsed, dict) else None
        return value if isinstance(value, str) else ""
