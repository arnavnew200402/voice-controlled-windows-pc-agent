"""Narrow Win32 adapters. No shell commands, clipboard access, or implicit targets."""

from __future__ import annotations

import ctypes
import os
import shutil
import time
import uuid
from pathlib import Path, PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field

from vox.agent.tools import ToolResult

KNOWN_FOLDERS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "A990AE9F-A03B-4E80-94BC-9912D7504104",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
    "home": "5E6C858F-0E22-4760-9AFE-EA3317B67173",
}


class WindowRef(BaseModel):
    """Local-only identity; never included in the model request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    hwnd: int = Field(gt=0)
    pid: int = Field(gt=0)
    created: int = Field(gt=0)
    focus_hwnd: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=300)
    window_class: str = Field(min_length=1, max_length=256)


DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


def valid_local_path(path: str) -> bool:
    if not path or len(path) > 1000 or any(ord(c) < 32 or c in '%*?"<>|' for c in path):
        return False
    if path.endswith((" ", ".")):
        return False
    p = PureWindowsPath(path)
    # No UNC/device/relative paths, alternate data streams, or parent traversal.
    if not p.is_absolute() or len(p.drive) != 2 or p.drive[1] != ":" or not p.drive[0].isalpha():
        return False
    for part in p.parts[1:]:
        if part in (".", "..") or ":" in part or part.endswith((" ", ".")):
            return False
        if part.casefold().split(".", 1)[0] in DEVICE_NAMES:
            return False
    return True


def _known_folder(name: str) -> str:
    if os.name != "nt" or name not in KNOWN_FOLDERS:
        raise OSError("Known folder not available")
    shell = ctypes.WinDLL("shell32", use_last_error=True)  # type: ignore[attr-defined]
    ole = ctypes.WinDLL("ole32", use_last_error=True)  # type: ignore[attr-defined]
    guid = ctypes.create_string_buffer(uuid.UUID(KNOWN_FOLDERS[name]).bytes_le, 16)
    pointer = ctypes.c_void_p()
    shell.SHGetKnownFolderPath.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell.SHGetKnownFolderPath.restype = ctypes.c_int32
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    if (
        shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer)) != 0
        or not pointer.value
    ):
        raise OSError("Known folder not available")
    try:
        return ctypes.wstring_at(pointer.value)
    finally:
        ole.CoTaskMemFree(pointer)


def resolve_folder(target: str) -> str:
    if os.name != "nt":
        raise OSError("Folder opening requires Windows")
    raw = _known_folder(target.lower()) if target.lower() in KNOWN_FOLDERS else target
    if not valid_local_path(raw):
        raise ValueError("Only local absolute folders are supported")
    p = Path(raw).resolve(strict=True)
    if not p.is_dir() or not valid_local_path(str(p)):
        raise ValueError("Folder does not exist or is not local")
    return str(p)


def open_resolved_folder(path: str) -> ToolResult:
    try:
        resolved = resolve_folder(path)
        if os.path.normcase(resolved) != os.path.normcase(path):
            return ToolResult(
                ok=False, evidence="Folder changed since approval; nothing was opened."
            )
        os.startfile(resolved)  # type: ignore[attr-defined]
        return ToolResult(
            ok=True,
            evidence="Windows was asked to open the approved folder; its window was not verified.",
        )
    except (OSError, ValueError):
        return ToolResult(ok=False, evidence="Could not open the approved local folder.")


DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
LONG = ctypes.c_int32
BOOL = ctypes.c_int32
HANDLE = ctypes.c_void_p


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", DWORD), ("high", DWORD)]


class _RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("flags", DWORD),
        ("active", HANDLE),
        ("focus", HANDLE),
        ("capture", HANDLE),
        ("menu", HANDLE),
        ("move", HANDLE),
        ("caret", HANDLE),
        ("rect", _RECT),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("vk", WORD),
        ("scan", WORD),
        ("flags", DWORD),
        ("time", DWORD),
        ("extra", ctypes.c_size_t),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouse_data", DWORD),
        ("flags", DWORD),
        ("time", DWORD),
        ("extra", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("msg", DWORD), ("low", WORD), ("high", WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("keyboard", _KEYBDINPUT), ("mouse", _MOUSEINPUT), ("hardware", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("kind", DWORD), ("value", _INPUTUNION)]


def _unicode_inputs(text: str) -> list[_INPUT]:
    encoded = text.encode("utf-16-le")
    inputs = []
    for i in range(0, len(encoded), 2):
        code = int.from_bytes(encoded[i : i + 2], "little")
        for flags in (0x0004, 0x0004 | 0x0002):
            item = _INPUT()
            item.kind = 1
            item.value.keyboard = _KEYBDINPUT(0, code, flags, 0, 0)
            inputs.append(item)
    return inputs


class WindowsWindows:
    """Enumerates only visible windows with a focused control and stable process identity."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows desktop required")
        self.user = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        u, k = self.user, self.kernel
        u.IsWindow.argtypes, u.IsWindow.restype = [HANDLE], BOOL
        u.IsWindowVisible.argtypes, u.IsWindowVisible.restype = [HANDLE], BOOL
        u.IsWindowEnabled.argtypes, u.IsWindowEnabled.restype = [HANDLE], BOOL
        u.IsIconic.argtypes, u.IsIconic.restype = [HANDLE], BOOL
        u.GetWindowTextLengthW.argtypes, u.GetWindowTextLengthW.restype = [HANDLE], ctypes.c_int
        u.GetWindowTextW.argtypes, u.GetWindowTextW.restype = (
            [HANDLE, ctypes.c_wchar_p, ctypes.c_int],
            ctypes.c_int,
        )
        u.GetClassNameW.argtypes, u.GetClassNameW.restype = (
            [HANDLE, ctypes.c_wchar_p, ctypes.c_int],
            ctypes.c_int,
        )
        u.GetWindowThreadProcessId.argtypes, u.GetWindowThreadProcessId.restype = (
            [HANDLE, ctypes.POINTER(DWORD)],
            DWORD,
        )
        u.GetGUIThreadInfo.argtypes, u.GetGUIThreadInfo.restype = (
            [DWORD, ctypes.POINTER(_GUITHREADINFO)],
            BOOL,
        )
        u.GetAncestor.argtypes, u.GetAncestor.restype = [HANDLE, DWORD], HANDLE
        u.SetForegroundWindow.argtypes, u.SetForegroundWindow.restype = [HANDLE], BOOL
        u.GetForegroundWindow.argtypes, u.GetForegroundWindow.restype = [], HANDLE
        u.SendInput.argtypes, u.SendInput.restype = (
            [DWORD, ctypes.POINTER(_INPUT), ctypes.c_int],
            DWORD,
        )
        u.ShowWindow.argtypes, u.ShowWindow.restype = [HANDLE, ctypes.c_int], BOOL
        u.PostMessageW.argtypes, u.PostMessageW.restype = (
            [HANDLE, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t],
            BOOL,
        )
        k.OpenProcess.argtypes, k.OpenProcess.restype = [DWORD, BOOL, DWORD], HANDLE
        k.GetProcessTimes.argtypes = [
            HANDLE,
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
        ]
        k.GetProcessTimes.restype = BOOL
        k.CloseHandle.argtypes, k.CloseHandle.restype = [HANDLE], BOOL

    def snapshot(self, hwnd: int) -> WindowRef | None:
        u, k = self.user, self.kernel
        if (
            not u.IsWindow(hwnd)
            or not u.IsWindowVisible(hwnd)
            or not u.IsWindowEnabled(hwnd)
            or u.IsIconic(hwnd)
        ):
            return None
        length = u.GetWindowTextLengthW(hwnd)
        if not 0 < length <= 300:
            return None
        title = ctypes.create_unicode_buffer(length + 1)
        classname = ctypes.create_unicode_buffer(256)
        if not u.GetWindowTextW(hwnd, title, len(title)) or not u.GetClassNameW(
            hwnd, classname, len(classname)
        ):
            return None
        # Control/format characters could hide or spoof the approval label.
        import unicodedata

        if any(
            unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in title.value + classname.value
        ):
            return None
        pid = DWORD()
        thread = u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not thread or not pid.value or pid.value == os.getpid():
            return None
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(info)
        if (
            not u.GetGUIThreadInfo(thread, ctypes.byref(info))
            or not info.focus
            or u.GetAncestor(info.focus, 2) != hwnd
        ):
            return None
        proc = k.OpenProcess(0x1000, False, pid.value)
        if not proc:
            return None
        try:
            creation, exit_time, kernel_time, user_time = (
                _FILETIME(),
                _FILETIME(),
                _FILETIME(),
                _FILETIME(),
            )
            if not k.GetProcessTimes(
                proc,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
            created = (creation.high << 32) | creation.low
        finally:
            k.CloseHandle(proc)
        try:
            return WindowRef(
                hwnd=int(hwnd),
                pid=pid.value,
                created=created,
                focus_hwnd=int(info.focus),
                title=title.value,
                window_class=classname.value,
            )
        except ValueError:
            return None

    def list_windows(self) -> list[WindowRef]:
        result: list[WindowRef] = []
        callback_type = ctypes.WINFUNCTYPE(BOOL, HANDLE, ctypes.c_ssize_t)  # type: ignore[attr-defined]

        @callback_type  # type: ignore[untyped-decorator]
        def callback(hwnd: int, _: int) -> int:
            item = self.snapshot(hwnd)
            if item is not None and len(result) < 100:
                result.append(item)
            return 1

        self.user.EnumWindows.argtypes, self.user.EnumWindows.restype = (
            [callback_type, ctypes.c_ssize_t],
            BOOL,
        )
        if not self.user.EnumWindows(callback, 0):
            raise OSError("Window enumeration failed")
        return result

    def type_text(self, target: WindowRef, text: str) -> ToolResult:
        if self.snapshot(target.hwnd) != target:
            return ToolResult(
                ok=False, evidence="Selected window or focused control changed. No text was sent."
            )
        if not self.user.SetForegroundWindow(target.hwnd):
            return ToolResult(
                ok=False,
                evidence="Windows would not activate the selected window. No text was sent.",
            )
        time.sleep(0.05)
        if self.user.GetForegroundWindow() != target.hwnd or self.snapshot(target.hwnd) != target:
            return ToolResult(
                ok=False, evidence="Selected window or focused control changed. No text was sent."
            )
        events = _unicode_inputs(text)
        batch = (_INPUT * len(events))(*events)
        sent = self.user.SendInput(len(events), batch, ctypes.sizeof(_INPUT))
        if sent != len(events):
            return ToolResult(
                ok=False,
                evidence="Windows accepted only part of the input; inspect the selected window.",
            )
        return ToolResult(
            ok=True,
            evidence="Input was sent to the selected window; the resulting text was not verified.",
        )

    def scroll(self, target: WindowRef, amount: int) -> ToolResult:
        if self.snapshot(target.hwnd) != target:
            return ToolResult(
                ok=False,
                evidence="Selected window or focused control changed. No scroll was sent.",
            )
        WHEEL_DELTA = 120
        for _ in range(abs(amount)):
            direction = 1 if amount > 0 else -1
            item = _INPUT()
            item.kind = 0
            item.value.mouse = _MOUSEINPUT(0, 0, direction * WHEEL_DELTA, 0x0800, 0, 0)
            batch = (_INPUT * 1)(item)
            sent = self.user.SendInput(1, batch, ctypes.sizeof(_INPUT))
            if sent != 1:
                return ToolResult(
                    ok=False, evidence="Windows accepted only part of the scroll input."
                )
        return ToolResult(
            ok=True,
            evidence="Scroll input was sent to the selected window; the result was not verified.",
        )

    def minimize(self, target: WindowRef) -> ToolResult:
        if self.snapshot(target.hwnd) != target:
            return ToolResult(ok=False, evidence="Selected window changed. Nothing was minimized.")
        if not self.user.ShowWindow(target.hwnd, 6):
            return ToolResult(ok=False, evidence="Windows would not minimize the selected window.")
        return ToolResult(ok=True, evidence="Selected window was minimized.")

    def maximize(self, target: WindowRef) -> ToolResult:
        if self.snapshot(target.hwnd) != target:
            return ToolResult(ok=False, evidence="Selected window changed. Nothing was maximized.")
        if not self.user.ShowWindow(target.hwnd, 3):
            return ToolResult(ok=False, evidence="Windows would not maximize the selected window.")
        return ToolResult(ok=True, evidence="Selected window was maximized.")

    def restore(self, target: WindowRef) -> ToolResult:
        if self.snapshot(target.hwnd) != target:
            return ToolResult(ok=False, evidence="Selected window changed. Nothing was restored.")
        if not self.user.ShowWindow(target.hwnd, 9):
            return ToolResult(ok=False, evidence="Windows would not restore the selected window.")
        return ToolResult(ok=True, evidence="Selected window was restored.")

    def close_window(self, target: WindowRef) -> ToolResult:
        if self.snapshot(target.hwnd) != target:
            return ToolResult(ok=False, evidence="Selected window changed. Nothing was closed.")
        if not self.user.PostMessageW(target.hwnd, 0x10, 0, 0):
            return ToolResult(ok=False, evidence="Windows would not accept the close request.")
        return ToolResult(
            ok=True,
            evidence="Close request was sent to the selected window; the window may ask for confirmation.",
        )

    def copy_file(self, source: str, destination: str) -> ToolResult:
        if not valid_local_path(source) or not valid_local_path(destination):
            return ToolResult(ok=False, evidence="Only local absolute paths are supported.")
        try:
            src = Path(source).resolve(strict=True)
            dst = Path(destination).resolve()
            if not src.is_file():
                return ToolResult(ok=False, evidence="Source file does not exist.")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return ToolResult(ok=True, evidence=f"File copied from {src} to {dst}.")
        except (OSError, ValueError, shutil.Error):
            return ToolResult(ok=False, evidence="Could not copy the file.")

    def move_file(self, source: str, destination: str) -> ToolResult:
        if not valid_local_path(source) or not valid_local_path(destination):
            return ToolResult(ok=False, evidence="Only local absolute paths are supported.")
        try:
            src = Path(source).resolve(strict=True)
            dst = Path(destination).resolve()
            if not src.is_file():
                return ToolResult(ok=False, evidence="Source file does not exist.")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return ToolResult(ok=True, evidence=f"File moved from {src} to {dst}.")
        except (OSError, ValueError, shutil.Error):
            return ToolResult(ok=False, evidence="Could not move the file.")

    def delete_file(self, path: str) -> ToolResult:
        if not valid_local_path(path):
            return ToolResult(ok=False, evidence="Only local absolute paths are supported.")
        try:
            target = Path(path).resolve(strict=True)
            if not target.is_file():
                return ToolResult(ok=False, evidence="File does not exist.")
            target.unlink()
            return ToolResult(ok=True, evidence=f"File deleted: {target}.")
        except (OSError, ValueError):
            return ToolResult(ok=False, evidence="Could not delete the file.")

    def screenshot(self, path: str) -> ToolResult:
        if not valid_local_path(path):
            return ToolResult(ok=False, evidence="Only local absolute paths are supported.")
        try:
            target = Path(path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            user = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
            gdi = ctypes.WinDLL("gdi32", use_last_error=True)  # type: ignore[attr-defined]
            src_dc = user.GetDC(0)
            height = user.GetSystemMetrics(78)
            width = user.GetSystemMetrics(77)
            dest_dc = gdi.CreateCompatibleDC(src_dc)
            bitmap = gdi.CreateCompatibleBitmap(src_dc, width, height)
            gdi.SelectObject(dest_dc, bitmap)
            gdi.BitBlt(dest_dc, 0, 0, width, height, src_dc, 0, 0, 0x00CC0020)
            target = target.with_suffix(".bmp")
            try:
                from PIL import Image  # type: ignore[import-not-found]

                img = Image.frombytes("RGB", (width, height), b"", "raw", "BGRX", 0, 1)
                img.save(str(target), "BMP")
            except ImportError:
                row_size = ((width * 3 + 3) // 4) * 4
                pixel_data = bytearray(row_size * height)
                gdi.GetDIBits(dest_dc, bitmap, 0, height, pixel_data, None, 0)
                with open(str(target), "wb") as f:
                    f.write(b"BM")
                    f.write((54 + len(pixel_data)).to_bytes(4, "little"))
                    f.write(b"\0\0\0\0")
                    f.write(b"\x36\x00\x00\x00")
                    f.write(b"\x28\x00\x00\x00")
                    f.write(width.to_bytes(4, "little"))
                    f.write(height.to_bytes(4, "little"))
                    f.write((1).to_bytes(2, "little"))
                    f.write((24).to_bytes(2, "little"))
                    f.write(b"\0\0\0\0")
                    f.write(len(pixel_data).to_bytes(4, "little"))
                    f.write((2835).to_bytes(4, "little"))
                    f.write((2835).to_bytes(4, "little"))
                    f.write(b"\0\0\0\0\0\0\0\0")
                    f.write(pixel_data)
            gdi.DeleteObject(bitmap)
            gdi.DeleteDC(dest_dc)
            user.ReleaseDC(0, src_dc)
            return ToolResult(ok=True, evidence=f"Screenshot saved to {target}.")
        except (OSError, ValueError, ImportError):
            return ToolResult(ok=False, evidence="Could not capture screenshot.")
