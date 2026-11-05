"""Windows DPAPI-protected, atomically replaced OAuth credential record."""

from __future__ import annotations

import ctypes
import json
import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vox.branding import APP_NAME


@dataclass(frozen=True)
class Session:
    client_id: str
    subject: str
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    id_token: str = field(repr=False)
    expires_at: float

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value or len(value) > 65536
            for value in (
                self.client_id,
                self.subject,
                self.access_token,
                self.refresh_token,
                self.id_token,
            )
        ):
            raise ValueError("invalid session")
        if type(self.expires_at) not in (int, float) or not 0 < self.expires_at < 100000000000:
            raise ValueError("invalid expiry")


class StorageError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise StorageError("Windows DPAPI is required for credential storage.")
    try:
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)  # type: ignore[attr-defined, unused-ignore]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined, unused-ignore]
        array = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        incoming = _Blob(len(data), array)
        outgoing = _Blob()
        if decrypt:
            fn = crypt.CryptUnprotectData
            fn.argtypes = [
                ctypes.POINTER(_Blob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(_Blob),
            ]
        else:
            fn = crypt.CryptProtectData
            fn.argtypes = [
                ctypes.POINTER(_Blob),
                ctypes.c_wchar_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(_Blob),
            ]
        fn.restype = ctypes.c_int
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not fn(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise StorageError("Could not protect or open the Windows credential record.")
        try:
            return ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            kernel.LocalFree(ctypes.cast(outgoing.pbData, ctypes.c_void_p))
    except OSError as exc:
        raise StorageError("Windows credential protection is unavailable.") from exc


def protect(data: bytes) -> bytes:
    return _dpapi(data, decrypt=False)


def unprotect(data: bytes) -> bytes:
    return _dpapi(data, decrypt=True)


class CredentialStore:
    def __init__(
        self,
        path: Path,
        *,
        encrypt: Callable[[bytes], bytes] = protect,
        decrypt: Callable[[bytes], bytes] = unprotect,
    ) -> None:
        self.path = path
        self._encrypt = encrypt
        self._decrypt = decrypt

    def load(self) -> tuple[str | None, Session | None]:
        if not self.path.exists():
            return None, None
        try:
            data = json.loads(self._decrypt(self.path.read_bytes()))
            host = data["host_id"]
            if not isinstance(host, str) or not host.startswith("urn:uuid:"):
                raise ValueError("invalid host")
            if uuid.UUID(host.removeprefix("urn:uuid:")).version != 4:
                raise ValueError("invalid host")
            value = data.get("session")
            if value is not None and not isinstance(value, dict):
                raise ValueError("invalid session")
            session = Session(**value) if value is not None else None
            return host, session
        except (OSError, ValueError, TypeError, KeyError, StorageError) as exc:
            raise StorageError("Could not read the protected sign-in record.") from exc

    def save(self, host: str, session: Session | None) -> None:
        try:
            payload = json.dumps(
                {"host_id": host, "session": asdict(session) if session else None}
            ).encode()
            encrypted = self._encrypt(payload)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            name: str | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as tmp:
                    name = tmp.name
                    tmp.write(encrypted)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(name, self.path)
            finally:
                if name is not None and os.path.exists(name):
                    os.unlink(name)
        except (OSError, ValueError, StorageError) as exc:
            raise StorageError("Could not save the protected sign-in record.") from exc


def windows_store() -> CredentialStore:
    if os.name != "nt":
        raise StorageError("ChatGPT sign-in currently requires Windows DPAPI.")
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise StorageError("LOCALAPPDATA is not set.")
    return CredentialStore(Path(root) / APP_NAME / "chatgpt.dat")
