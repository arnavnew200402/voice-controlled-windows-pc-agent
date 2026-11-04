"""Restricted Windows launcher. It never uses a shell, PATH or model-supplied path."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from collections.abc import Callable
from typing import Protocol

from vox.agent.tools import ToolResult


class Process(Protocol):
    pid: int

    def poll(self) -> int | None: ...


def system_directory() -> str:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    func = kernel.GetSystemDirectoryW
    func.argtypes = [ctypes.POINTER(ctypes.c_wchar), ctypes.c_uint]
    func.restype = ctypes.c_uint
    buf = ctypes.create_unicode_buffer(32768)
    length = func(buf, len(buf))
    if not length or length >= len(buf):
        raise OSError("Could not determine the Windows system directory")
    return str(buf.value)


def foreground_pid() -> int:
    user = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    user.GetForegroundWindow.argtypes = []
    user.GetForegroundWindow.restype = ctypes.c_void_p
    user.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user.GetWindowThreadProcessId.restype = ctypes.c_ulong
    window = user.GetForegroundWindow()
    if not window:
        return 0
    pid = ctypes.c_ulong()
    if not user.GetWindowThreadProcessId(window, ctypes.byref(pid)):
        return 0
    return int(pid.value)


def launch(executable: str) -> Process:
    return subprocess.Popen([executable], shell=False, close_fds=True)


class WindowsNotepadBackend:
    """T0 launcher; failure to verify the foreground is reported as failure.

    Notepad may delegate to an existing process on newer Windows versions; this
    conservative check can therefore report an unverified launch even if it opened.
    """

    def __init__(
        self,
        *,
        system_dir: Callable[[], str] = system_directory,
        launcher: Callable[[str], Process] = launch,
        foreground: Callable[[], int] = foreground_pid,
        platform: str = os.name,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._system_dir = system_dir
        self._launcher = launcher
        self._foreground = foreground
        self._platform = platform
        self._clock = clock
        self._sleep = sleep

    def open_notepad(self) -> ToolResult:
        if self._platform != "nt":
            return ToolResult(ok=False, evidence="Opening Notepad requires Windows.")
        try:
            executable = os.path.join(self._system_dir(), "notepad.exe")
            proc = self._launcher(executable)
            deadline = self._clock() + 2.0
            while self._clock() < deadline:
                if proc.poll() is not None:
                    break
                if self._foreground() == proc.pid and proc.poll() is None:
                    return ToolResult(ok=True, evidence="Notepad opened and is in the foreground.")
                self._sleep(0.05)
        except (OSError, ValueError):
            return ToolResult(ok=False, evidence="Could not launch or verify Windows Notepad.")
        return ToolResult(
            ok=False,
            evidence="Notepad was launched, but I could not verify its foreground window.",
        )
