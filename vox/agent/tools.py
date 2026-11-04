"""A closed, typed registry containing only the experimental Notepad tool."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class OpenAppArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: Literal["Notepad"] = Field(description="Only the built-in Windows Notepad is supported.")


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ok: bool
    evidence: str
    simulated: bool = False


class AppBackend(Protocol):
    def open_notepad(self) -> ToolResult: ...


class ToolRegistry:
    """The only model-visible real capability: open Windows Notepad.

    This is not yet the Wyzer registry, a general safety policy, or a plugin API.
    No free-form executables, paths or shell commands can be passed to it.
    """

    def __init__(self, backend: AppBackend) -> None:
        self._backend = backend

    def schemas(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Open Windows Notepad. Other applications are unavailable.",
                    "parameters": OpenAppArgs.model_json_schema(),
                },
            }
        ]

    def execute(self, name: str, arguments: object) -> ToolResult:
        if name != "open_app":
            return ToolResult(ok=False, evidence="That tool is not available.")
        try:
            OpenAppArgs.model_validate(arguments)
        except ValidationError:
            return ToolResult(
                ok=False, evidence="The application request was invalid or unsupported."
            )
        return self._backend.open_notepad()


class DryRunBackend:
    def open_notepad(self) -> ToolResult:
        return ToolResult(
            ok=True,
            simulated=True,
            evidence="Dry run: would open Notepad; no application was launched.",
        )
