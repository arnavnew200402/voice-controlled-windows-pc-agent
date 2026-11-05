"""In-memory, single-use approvals for already-validated tool calls.

The caller is responsible for classifying the action and establishing the origin
of input events. In particular, a string saying "click" is not proof of physical
input. This module does not execute tools or provide an audit log.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from pydantic import BaseModel


class Tier(IntEnum):
    SAFE = 0
    CONFIRM = 1
    CONFIRM_HARD = 2
    BLOCKED = 3


class Via(StrEnum):
    VOICE = "voice"
    CLICK = "click"
    HOTKEY = "hotkey"


class Status(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"


def call_hash(tool: str, args: BaseModel) -> str:
    """Hash canonical JSON of a validated model, never raw model-generated args."""
    if not isinstance(args, BaseModel):
        raise TypeError("args must be a validated Pydantic model")
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("tool must be a non-empty name")
    data = args.model_dump(mode="json", round_trip=True)
    encoded = json.dumps(
        [tool, data], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ApprovalView:
    id: str
    tool: str
    tier: Tier
    expires_at: float  # UTC Unix time, for display only
    status: Status
    via: str | None


@dataclass
class _Entry:
    id: str
    tool: str
    args_hash: str
    tier: Tier
    deadline: float  # monotonic time, used for all authorization decisions
    expires_at: float
    status: Status = Status.PENDING
    via: str | None = None

    def view(self) -> ApprovalView:
        return ApprovalView(self.id, self.tool, self.tier, self.expires_at, self.status, self.via)


class ApprovalStore:
    """Thread-safe approval state. Restarting the process invalidates all approvals."""

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
        capacity: int = 1024,
    ) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._clock = monotonic
        self._wall_time = wall_time
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def request(
        self, tool: str, args: BaseModel, tier: Tier, *, ttl: float | None = None
    ) -> ApprovalView:
        if not isinstance(tier, Tier) or tier not in (Tier.CONFIRM, Tier.CONFIRM_HARD):
            raise ValueError("only T1 and T2 can request approval")
        maximum = 15.0 if tier == Tier.CONFIRM else 30.0
        lifetime = maximum if ttl is None else ttl
        if not math.isfinite(lifetime) or not 0 < lifetime <= maximum:
            raise ValueError("ttl must be positive and no greater than the tier limit")
        digest = call_hash(tool, args)
        with self._lock:
            if len(self._entries) >= self._capacity:
                # Expired and resolved entries cannot authorize a call. Remove them
                # only under pressure; never discard a pending or live approval.
                for item in self._entries.values():
                    self._expire(item)
                self._entries = {
                    key: item
                    for key, item in self._entries.items()
                    if item.status in (Status.PENDING, Status.APPROVED)
                }
                if len(self._entries) >= self._capacity:
                    raise RuntimeError("approval capacity reached")
            entry = _Entry(
                id=uuid.uuid4().hex,
                tool=tool,
                args_hash=digest,
                tier=tier,
                deadline=self._clock() + lifetime,
                expires_at=self._wall_time() + lifetime,
            )
            self._entries[entry.id] = entry
            return entry.view()

    def _expire(self, entry: _Entry) -> None:
        if entry.status in (Status.PENDING, Status.APPROVED) and self._clock() >= entry.deadline:
            entry.status = Status.EXPIRED
            entry.via = "timeout"

    def get(self, approval_id: str) -> ApprovalView | None:
        with self._lock:
            entry = self._entries.get(approval_id)
            if entry is None:
                return None
            self._expire(entry)
            return entry.view()

    def resolve(
        self,
        approval_id: str,
        *,
        approve: bool,
        via: Via,
        loopback_clear: bool = False,
    ) -> bool:
        """Resolve once. Voice approval defaults to deny unless loopback is checked clear.

        Only a trusted input adapter may call this method; it must never accept a
        model- or network-supplied `via` or `loopback_clear` as evidence.
        """
        if (
            type(approve) is not bool
            or not isinstance(via, Via)
            or type(loopback_clear) is not bool
        ):
            return False
        with self._lock:
            entry = self._entries.get(approval_id)
            if entry is None:
                return False
            self._expire(entry)
            if entry.status != Status.PENDING:
                return False
            if approve and entry.tier == Tier.CONFIRM_HARD and via not in (Via.CLICK, Via.HOTKEY):
                return False
            if approve and via == Via.VOICE and not loopback_clear:
                return False
            entry.status = Status.APPROVED if approve else Status.DENIED
            entry.via = via.value
            return True

    def consume(self, approval_id: str, tool: str, args: BaseModel, *, tier: Tier) -> bool:
        """Atomically consume only an approval for the same call and effective tier."""
        if not isinstance(tier, Tier):
            return False
        digest = call_hash(tool, args)
        with self._lock:
            entry = self._entries.get(approval_id)
            if entry is None:
                return False
            self._expire(entry)
            if (
                entry.status != Status.APPROVED
                or entry.tool != tool
                or entry.tier != tier
                or not hmac.compare_digest(entry.args_hash, digest)
            ):
                return False
            entry.status = Status.CONSUMED
            return True

    def deny_all(self) -> int:
        """Revoke pending and approved-but-not-consumed calls on stop/cancel."""
        with self._lock:
            count = 0
            for entry in self._entries.values():
                self._expire(entry)
                if entry.status in (Status.PENDING, Status.APPROVED):
                    entry.status = Status.DENIED
                    entry.via = "stop"
                    count += 1
            return count
