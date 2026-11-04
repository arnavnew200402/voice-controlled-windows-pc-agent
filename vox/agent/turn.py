"""One local LLM-first turn; intentionally limited to a single safe tool call."""

from __future__ import annotations

from collections.abc import Callable

from vox.agent.provider import ChatProvider, ProviderError
from vox.agent.tools import ToolRegistry, ToolResult


def run_turn(
    text: str,
    provider: ChatProvider,
    registry: ToolRegistry,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> ToolResult:
    if not text.strip() or len(text) > 4000:
        return ToolResult(ok=False, evidence="Enter a request of at most 4000 characters.")
    if cancelled():
        return ToolResult(ok=False, evidence="Request cancelled before the model call.")
    try:
        response = provider.chat(text, registry.schemas())
    except ProviderError:
        return ToolResult(
            ok=False,
            evidence="The selected provider is unavailable. Check sign-in, connectivity and model access.",
        )
    if cancelled():
        return ToolResult(ok=False, evidence="Request cancelled before any tool was run.")
    message = response.get("message")
    if not isinstance(message, dict):
        return ToolResult(ok=False, evidence="The provider returned an invalid response.")
    calls = message.get("tool_calls", [])
    if not isinstance(calls, list) or len(calls) != 1:
        # Do not relay an unverified model claim that it operated the PC.
        return ToolResult(
            ok=False, evidence="No supported action was selected. Only Notepad is available."
        )
    call = calls[0]
    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
        return ToolResult(ok=False, evidence="The provider returned an invalid tool call.")
    function = call["function"]
    name, args = function.get("name"), function.get("arguments")
    if not isinstance(name, str):
        return ToolResult(ok=False, evidence="The provider returned an invalid tool call.")
    if cancelled():
        return ToolResult(ok=False, evidence="Request cancelled before any tool was run.")
    return registry.execute(name, args)
