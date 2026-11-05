"""User-supplied Groq key, protected at rest by Windows DPAPI."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from vox.agent.auth_storage import StorageError, protect, unprotect


class GroqKeyStore:
    def __init__(
        self,
        path: Path,
        *,
        encrypt: Callable[[bytes], bytes] = protect,
        decrypt: Callable[[bytes], bytes] = unprotect,
    ) -> None:
        self.path, self._encrypt, self._decrypt = path, encrypt, decrypt

    @staticmethod
    def validate(key: str) -> None:
        if (
            not key
            or len(key) > 512
            or not key.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in key)
        ):
            raise ValueError("Enter a valid Groq API key without spaces.")

    def save(self, key: str) -> None:
        self.validate(key)
        name = None
        try:
            encrypted = self._encrypt(key.encode("ascii"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as f:
                name = f.name
                f.write(encrypted)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        except (OSError, StorageError) as exc:
            raise StorageError("Could not save the protected Groq key.") from exc
        finally:
            if name is not None and os.path.exists(name):
                os.unlink(name)

    def load(self) -> str:
        try:
            key = self._decrypt(self.path.read_bytes()).decode("ascii")
            self.validate(key)
            return key
        except (OSError, UnicodeError, ValueError, StorageError) as exc:
            raise StorageError("Add your Groq API key first.") from exc

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Could not remove the Groq key.") from exc


def windows_groq_store() -> GroqKeyStore:
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        raise StorageError("Windows DPAPI is required for the Groq key.")
    return GroqKeyStore(Path(os.environ["LOCALAPPDATA"]) / "vox" / "groq.key")
