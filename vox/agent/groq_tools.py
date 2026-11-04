"""Closed registry for the Groq voice slice. Browser navigation needs confirmation."""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import time
import unicodedata
import webbrowser
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.agent.windows import foreground_pid, system_directory
from vox.agent.windows_control import (
    KNOWN_FOLDERS,
    WindowRef,
    WindowsWindows,
    open_resolved_folder,
    resolve_folder,
    valid_local_path,
)
from vox.approvals import ApprovalStore, Tier, Via


class AppArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: Literal["Notepad", "Calculator", "Paint"]


class WebsiteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    url: str = Field(
        min_length=9,
        max_length=300,
        description="An HTTPS address, without credentials or a local IP address.",
    )

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        if not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in value):
            raise ValueError("invalid URL")
        try:
            u = urlsplit(value)
            if (
                u.scheme != "https"
                or not u.hostname
                or u.username
                or u.password
                or u.port not in (None, 443)
            ):
                raise ValueError("invalid URL")
            host = u.hostname.rstrip(".").lower()
            if host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
                raise ValueError("local addresses not supported")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError("IP addresses not supported")
            if all(c.isdigit() or c == "." for c in host):
                raise ValueError("numeric hosts not supported")
            if any(not (c.isalnum() or c in ".-") for c in host):
                raise ValueError("invalid hostname")
        except ValueError as exc:
            raise ValueError("Invalid or unsupported HTTPS address") from exc
        return value


class FolderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target: str = Field(
        min_length=1,
        max_length=1000,
        description="A known folder (Downloads, Documents, Desktop, Pictures, Music, Videos, Home), or its exact absolute local Windows path.",
    )

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if value.lower() not in KNOWN_FOLDERS and not valid_local_path(value):
            raise ValueError("A known folder or absolute local Windows path is required")
        return value


class FolderBound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not valid_local_path(value):
            raise ValueError("Invalid resolved path")
        return value


class TypingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    text: str = Field(
        min_length=1,
        max_length=300,
        description="Exact text to type, without Enter, Tab or other control characters.",
    )
    target_hint: str = Field(
        default="",
        max_length=120,
        description="The app or window mentioned by the user, if any; the user chooses the actual target locally.",
    )

    @field_validator("text", "target_hint")
    @classmethod
    def visible_text(cls, value: str) -> str:
        if any(unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in value):
            raise ValueError("Control and hidden formatting characters are not supported")
        return value


class TypingBound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    text: str
    window: WindowRef

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return TypingRequest(text=value).text


class ScrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    amount: int = Field(
        ge=-10, le=10, description="Scroll lines; negative scrolls up, positive scrolls down."
    )
    target_hint: str = Field(
        default="", max_length=120, description="The app or window mentioned by the user, if any."
    )


class ScrollBound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    amount: int
    window: WindowRef


class WindowActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target_hint: str = Field(
        default="", max_length=120, description="The app or window mentioned by the user, if any."
    )


class WindowActionBound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    window: WindowRef


@dataclass(frozen=True)
class PlannedAction:
    name: str
    args: BaseModel
    tier: Tier

    @property
    def description(self) -> str:
        if isinstance(self.args, AppArgs):
            return f"Open Windows {self.args.name}."
        if isinstance(self.args, WebsiteArgs):
            return f"Open this website in your browser:\n{self.args.url}"
        if isinstance(self.args, FolderBound):
            return f"Open this local folder:\n{self.args.path}"
        if isinstance(self.args, TypingRequest):
            hint = f"\nRequested app: {self.args.target_hint}" if self.args.target_hint else ""
            return f"Type this exact text in the window you select:\n{self.args.text}{hint}"
        if isinstance(self.args, TypingBound):
            return f"Type this exact text in {self.args.window.title}:\n{self.args.text}"
        if isinstance(self.args, ScrollRequest):
            hint = f"\nRequested app: {self.args.target_hint}" if self.args.target_hint else ""
            return f"Scroll {self.args.amount:+d} lines in the window you select.{hint}"
        if isinstance(self.args, ScrollBound):
            return f"Scroll {self.args.amount:+d} lines in {self.args.window.title}."
        if isinstance(self.args, WindowActionRequest):
            hint = f"\nRequested app: {self.args.target_hint}" if self.args.target_hint else ""
            return f"Control the window you select.{hint}"
        if isinstance(self.args, WindowActionBound):
            return f"Control the selected window: {self.args.window.title}."
        return "Unsupported action."


class DesktopBackend(Protocol):
    def open_app(self, name: str) -> ToolResult: ...
    def open_website(self, url: str) -> ToolResult: ...
    def resolve_folder(self, target: str) -> str: ...
    def open_folder(self, path: str) -> ToolResult: ...
    def list_windows(self) -> list[WindowRef]: ...
    def type_text(self, target: WindowRef, text: str) -> ToolResult: ...
    def scroll(self, target: WindowRef, amount: int) -> ToolResult: ...
    def minimize(self, target: WindowRef) -> ToolResult: ...
    def maximize(self, target: WindowRef) -> ToolResult: ...
    def restore(self, target: WindowRef) -> ToolResult: ...
    def close_window(self, target: WindowRef) -> ToolResult: ...


class WindowsDesktopBackend:
    def open_app(self, name: str) -> ToolResult:
        allowed = {"Notepad": "notepad.exe", "Calculator": "calc.exe", "Paint": "mspaint.exe"}
        if os.name != "nt" or name not in allowed:
            return ToolResult(ok=False, evidence="This Windows application is not available.")
        try:
            proc = subprocess.Popen(
                [os.path.join(system_directory(), allowed[name])], shell=False, close_fds=True
            )
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                if foreground_pid() == proc.pid:
                    return ToolResult(ok=True, evidence=f"{name} opened in the foreground.")
                time.sleep(0.05)
            return ToolResult(
                ok=False, evidence=f"{name} was launched, but its window could not be verified."
            )
        except (OSError, ValueError):
            return ToolResult(ok=False, evidence=f"Could not launch or verify {name}.")

    def open_website(self, url: str) -> ToolResult:
        if os.name != "nt":
            return ToolResult(ok=False, evidence="Opening websites requires Windows.")
        try:
            if webbrowser.open(url, new=2):
                return ToolResult(
                    ok=True,
                    evidence="The browser was asked to open the approved website; page load was not verified.",
                )
        except (OSError, webbrowser.Error):
            pass
        return ToolResult(ok=False, evidence="Could not open the approved website.")

    def resolve_folder(self, target: str) -> str:
        return resolve_folder(target)

    def open_folder(self, path: str) -> ToolResult:
        return open_resolved_folder(path)

    def list_windows(self) -> list[WindowRef]:
        try:
            return WindowsWindows().list_windows()
        except OSError:
            return []

    def type_text(self, target: WindowRef, text: str) -> ToolResult:
        try:
            return WindowsWindows().type_text(target, text)
        except OSError:
            return ToolResult(ok=False, evidence="Windows input is unavailable. No text was sent.")

    def scroll(self, target: WindowRef, amount: int) -> ToolResult:
        try:
            return WindowsWindows().scroll(target, amount)
        except OSError:
            return ToolResult(
                ok=False, evidence="Windows scroll is unavailable. No scroll was sent."
            )

    def minimize(self, target: WindowRef) -> ToolResult:
        try:
            return WindowsWindows().minimize(target)
        except OSError:
            return ToolResult(
                ok=False, evidence="Windows window control is unavailable. Nothing was minimized."
            )

    def maximize(self, target: WindowRef) -> ToolResult:
        try:
            return WindowsWindows().maximize(target)
        except OSError:
            return ToolResult(
                ok=False, evidence="Windows window control is unavailable. Nothing was maximized."
            )

    def restore(self, target: WindowRef) -> ToolResult:
        try:
            return WindowsWindows().restore(target)
        except OSError:
            return ToolResult(
                ok=False, evidence="Windows window control is unavailable. Nothing was restored."
            )

    def close_window(self, target: WindowRef) -> ToolResult:
        try:
            return WindowsWindows().close_window(target)
        except OSError:
            return ToolResult(
                ok=False, evidence="Windows window control is unavailable. Nothing was closed."
            )


class GroqRegistry:
    def __init__(self, backend: DesktopBackend) -> None:
        self._backend = backend
        self.approvals = ApprovalStore()

    def request_approval(self, action: PlannedAction) -> str:
        allowed = (
            (action.name == "open_website" and isinstance(action.args, WebsiteArgs))
            or (action.name == "open_folder" and isinstance(action.args, FolderBound))
            or (action.name == "type_text" and isinstance(action.args, TypingBound))
            or (action.name == "scroll" and isinstance(action.args, ScrollBound))
            or (
                action.name
                in ("minimize_window", "maximize_window", "restore_window", "close_window")
                and isinstance(action.args, WindowActionBound)
            )
        )
        if not allowed or action.tier is not Tier.CONFIRM:
            raise ValueError("Action does not support approval")
        return self.approvals.request(action.name, action.args, action.tier).id

    def list_windows(self) -> list[WindowRef]:
        return self._backend.list_windows()

    def bind_typing(self, action: PlannedAction, window: WindowRef) -> PlannedAction:
        if (
            action.name != "type_text"
            or action.tier is not Tier.CONFIRM
            or not isinstance(action.args, TypingRequest)
        ):
            raise ValueError("Action is not a typing request")
        return PlannedAction(
            "type_text", TypingBound(text=action.args.text, window=window), Tier.CONFIRM
        )

    def bind_scroll(self, action: PlannedAction, window: WindowRef) -> PlannedAction:
        if (
            action.name != "scroll"
            or action.tier is not Tier.CONFIRM
            or not isinstance(action.args, ScrollRequest)
        ):
            raise ValueError("Action is not a scroll request")
        return PlannedAction(
            "scroll", ScrollBound(amount=action.args.amount, window=window), Tier.CONFIRM
        )

    def bind_window_action(self, action: PlannedAction, window: WindowRef) -> PlannedAction:
        if (
            action.name
            not in ("minimize_window", "maximize_window", "restore_window", "close_window")
            or action.tier is not Tier.CONFIRM
            or not isinstance(action.args, WindowActionRequest)
        ):
            raise ValueError("Action is not a window control request")
        return PlannedAction(action.name, WindowActionBound(window=window), Tier.CONFIRM)

    def resolve_approval(self, approval_id: str, approve: bool) -> bool:
        return self.approvals.resolve(approval_id, approve=approve, via=Via.CLICK)

    def schemas(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Open one of the supported built-in Windows applications.",
                    "parameters": AppArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "open_website",
                    "description": "Ask the user for permission to open a specific HTTPS website in their browser.",
                    "parameters": WebsiteArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "open_folder",
                    "description": "Open a known Windows folder or a specified absolute local folder. The user must approve the resolved path.",
                    "parameters": FolderRequest.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "type_text",
                    "description": "Type the exact requested text into a window selected and approved by the user. Cannot press Enter or Tab.",
                    "parameters": TypingRequest.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scroll",
                    "description": "Scroll up or down in a window selected and approved by the user.",
                    "parameters": ScrollRequest.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "minimize_window",
                    "description": "Minimize a window selected and approved by the user.",
                    "parameters": WindowActionRequest.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maximize_window",
                    "description": "Maximize a window selected and approved by the user.",
                    "parameters": WindowActionRequest.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "restore_window",
                    "description": "Restore a minimized or maximized window selected and approved by the user.",
                    "parameters": WindowActionRequest.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "close_window",
                    "description": "Send a close request to a window selected and approved by the user. The window may ask for confirmation.",
                    "parameters": WindowActionRequest.model_json_schema(),
                },
            },
        ]

    def plan(self, message: dict[str, object]) -> PlannedAction:
        calls = message.get("tool_calls")
        if (
            not isinstance(calls, list)
            or len(calls) != 1
            or not isinstance(calls[0], dict)
            or calls[0].get("type") != "function"
        ):
            raise ProviderError(
                "No single supported action was selected. No PC action was performed."
            )
        call = calls[0].get("function")
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("arguments"), str)
            or len(call["arguments"]) > 4096
        ):
            raise ProviderError("Groq returned an invalid action.")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate argument")
                result[key] = value
            return result

        try:
            raw = json.loads(call["arguments"], object_pairs_hook=unique)
            if call.get("name") == "open_app":
                return PlannedAction("open_app", AppArgs.model_validate(raw), Tier.SAFE)
            if call.get("name") == "open_website":
                return PlannedAction("open_website", WebsiteArgs.model_validate(raw), Tier.CONFIRM)
            if call.get("name") == "open_folder":
                request = FolderRequest.model_validate(raw)
                return PlannedAction(
                    "open_folder",
                    FolderBound(path=self._backend.resolve_folder(request.target)),
                    Tier.CONFIRM,
                )
            if call.get("name") == "type_text":
                return PlannedAction("type_text", TypingRequest.model_validate(raw), Tier.CONFIRM)
            if call.get("name") == "scroll":
                return PlannedAction("scroll", ScrollRequest.model_validate(raw), Tier.CONFIRM)
            if call.get("name") in (
                "minimize_window",
                "maximize_window",
                "restore_window",
                "close_window",
            ):
                return PlannedAction(
                    call["name"], WindowActionRequest.model_validate(raw), Tier.CONFIRM
                )
        except (ValueError, ValidationError, OSError) as exc:
            raise ProviderError("Groq returned invalid or unsupported action arguments.") from exc
        raise ProviderError("That action is not supported.")

    def execute(self, action: PlannedAction, approval_id: str | None = None) -> ToolResult:
        # Type/name/tier must match a validated registry action even after approval.
        if (
            action.name == "open_app"
            and action.tier is Tier.SAFE
            and isinstance(action.args, AppArgs)
        ):
            return self._backend.open_app(action.args.name)
        allowed = (
            (action.name == "open_website" and isinstance(action.args, WebsiteArgs))
            or (action.name == "open_folder" and isinstance(action.args, FolderBound))
            or (action.name == "type_text" and isinstance(action.args, TypingBound))
            or (action.name == "scroll" and isinstance(action.args, ScrollBound))
            or (
                action.name
                in ("minimize_window", "maximize_window", "restore_window", "close_window")
                and isinstance(action.args, WindowActionBound)
            )
        )
        if allowed and action.tier is Tier.CONFIRM:
            if not approval_id or not self.approvals.consume(
                approval_id, action.name, action.args, tier=action.tier
            ):
                return ToolResult(
                    ok=False, evidence="Approval is missing or expired. No action was performed."
                )
            if isinstance(action.args, WebsiteArgs):
                return self._backend.open_website(action.args.url)
            if isinstance(action.args, FolderBound):
                return self._backend.open_folder(action.args.path)
            if isinstance(action.args, TypingBound):
                return self._backend.type_text(action.args.window, action.args.text)
            if isinstance(action.args, ScrollBound):
                return self._backend.scroll(action.args.window, action.args.amount)
            if isinstance(action.args, WindowActionBound):
                if action.name == "minimize_window":
                    return self._backend.minimize(action.args.window)
                if action.name == "maximize_window":
                    return self._backend.maximize(action.args.window)
                if action.name == "restore_window":
                    return self._backend.restore(action.args.window)
                if action.name == "close_window":
                    return self._backend.close_window(action.args.window)
        return ToolResult(ok=False, evidence="Unsupported action.")
