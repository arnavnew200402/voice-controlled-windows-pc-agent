"""Shared contract for model providers."""

from typing import Any, Protocol


class ProviderError(RuntimeError):
    pass


class ChatProvider(Protocol):
    def chat(self, text: str, schemas: list[dict[str, object]]) -> dict[str, Any]: ...
