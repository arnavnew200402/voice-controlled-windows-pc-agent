"""Entity registry: the deterministic memory behind "it"/"the second one".

Windows, apps, files, monitors, tabs, numbered results and completed
actions that Vox has recently mentioned or touched, each with an id and a
TTL. Written only from tool/UI events (never by an LLM); stale facts are
hidden from resolution unless explicitly requested — desktop state must be
re-read before consequential actions (spec 4.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from vox.engine.clock import Clock, SystemClock

EntityKind = Literal["window", "app", "file", "monitor", "tab", "result_item", "action"]

_PREFIX: dict[EntityKind, str] = {
    "window": "win",
    "app": "app",
    "file": "file",
    "monitor": "mon",
    "tab": "tab",
    "result_item": "item",
    "action": "act",
}

DEFAULT_TTL_S = 300.0


@dataclass
class Entity:
    id: str
    kind: EntityKind
    label: str
    data: dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0
    ttl_s: float = DEFAULT_TTL_S

    def fresh(self, now: float) -> bool:
        return now - self.registered_at <= self.ttl_s

    def age(self, now: float) -> float:
        return max(0.0, now - self.registered_at)


class EntityRegistry:
    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._by_id: dict[str, Entity] = {}
        self._order: dict[EntityKind, list[str]] = {kind: [] for kind in _PREFIX}
        self._counters: dict[EntityKind, int] = {kind: 0 for kind in _PREFIX}

    def register(
        self,
        kind: EntityKind,
        label: str,
        data: dict[str, Any] | None = None,
        *,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> Entity:
        self._counters[kind] += 1
        entity = Entity(
            id=f"{_PREFIX[kind]}-{self._counters[kind]}",
            kind=kind,
            label=label,
            data=dict(data or {}),
            registered_at=self._clock.monotonic(),
            ttl_s=ttl_s,
        )
        self._by_id[entity.id] = entity
        self._order[kind].append(entity.id)
        return entity

    def get(self, entity_id: str) -> Entity | None:
        return self._by_id.get(entity_id)

    def by_kind(self, kind: EntityKind, *, fresh_only: bool = True) -> list[Entity]:
        """Entities of a kind in mention order (oldest first)."""
        now = self._clock.monotonic()
        return [
            self._by_id[entity_id]
            for entity_id in self._order[kind]
            if not fresh_only or self._by_id[entity_id].fresh(now)
        ]

    def last(self, kind: EntityKind, *, fresh_only: bool = True) -> Entity | None:
        items = self.by_kind(kind, fresh_only=fresh_only)
        return items[-1] if items else None

    def ordinal(self, kind: EntityKind, index: int, *, fresh_only: bool = True) -> Entity | None:
        """1-based "the second one" over mention order."""
        items = self.by_kind(kind, fresh_only=fresh_only)
        return items[index - 1] if 1 <= index <= len(items) else None

    def other(
        self, kind: EntityKind, exclude_id: str | None, *, fresh_only: bool = True
    ) -> Entity | None:
        """Most recent entity of the kind that is not ``exclude_id``."""
        for entity in reversed(self.by_kind(kind, fresh_only=fresh_only)):
            if entity.id != exclude_id:
                return entity
        return None

    def register_action(self, standalone_command: str, evidence: str = "") -> Entity:
        return self.register(
            "action",
            standalone_command,
            {"evidence": evidence},
            ttl_s=1800.0,
        )

    def forget(self, entity_id: str) -> None:
        entity = self._by_id.pop(entity_id, None)
        if entity is not None and entity_id in self._order[entity.kind]:
            self._order[entity.kind].remove(entity_id)

    def clear(self) -> None:
        self._by_id.clear()
        for ids in self._order.values():
            ids.clear()
