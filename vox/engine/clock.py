"""Injectable clocks so engine code never calls time.time() directly.

Production uses :class:`SystemClock`; the replay harness uses
:class:`VirtualClock` to run scripted scenarios in deterministic virtual
time (spec 4.1/§6).
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def wall(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()


class VirtualClock:
    """Manually advanced clock; monotonic and wall move together."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def wall(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("VirtualClock cannot move backwards")
        self._now += seconds
        return self._now
