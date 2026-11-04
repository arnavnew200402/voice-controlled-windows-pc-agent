"""Closed registry for the Groq voice slice. Browser navigation needs confirmation."""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.agent.windows import foreground_pid, system_directory
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
        return "Unsupported action."


class DesktopBackend(Protocol):
    def open_app(self, name: str) -> ToolResult: ...
    def open_website(self, url: str) -> ToolResult: ...


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


class GroqRegistry:
    def __init__(self, backend: DesktopBackend) -> None:
        self._backend = backend
        self.approvals = ApprovalStore()

    def request_approval(self, action: PlannedAction) -> str:
        if (
            action.name != "open_website"
            or action.tier is not Tier.CONFIRM
            or not isinstance(action.args, WebsiteArgs)
        ):
            raise ValueError("Action does not support approval")
        return self.approvals.request(action.name, action.args, action.tier).id

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
        except (ValueError, ValidationError) as exc:
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
        if (
            action.name == "open_website"
            and action.tier is Tier.CONFIRM
            and isinstance(action.args, WebsiteArgs)
        ):
            if not approval_id or not self.approvals.consume(
                approval_id, action.name, action.args, tier=action.tier
            ):
                return ToolResult(
                    ok=False,
                    evidence="Website approval is missing or expired. No action was performed.",
                )
            return self._backend.open_website(action.args.url)
        return ToolResult(ok=False, evidence="Unsupported action.")
