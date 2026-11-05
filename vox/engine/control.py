"""Deterministic control plane: the L-02 closed set, nothing more.

Matches only whole short utterances against the i18n phrase tables (plus a
stop-family prefix rule of at most three tokens, so "cancel the download"
stops the current turn). It never selects tools or extracts arguments.
Approval responses are classified only while an approval is pending, and
classification alone never approves anything: the shipped policy remains
click-approval until a later phase explicitly wires voice responses with
its own tests (LE decisions, 2026-11-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vox.engine.endpointing import tokens
from vox.engine.i18n import CONTROL_PHRASES, DENY_TOKENS


class ControlAction(StrEnum):
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    STATUS = "status"
    MUTE = "mute"
    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True)
class ControlResult:
    action: ControlAction
    lang: str


# Exact-phrase lookup -> (action, lang), built once from the i18n tables.
_EXACT: dict[str, ControlResult] = {}
for _lang, _categories in CONTROL_PHRASES.items():
    for _category, _phrases in _categories.items():
        for _phrase in _phrases:
            _EXACT[" ".join(tokens(_phrase))] = ControlResult(ControlAction(_category), _lang)

_APPROVAL_CATEGORIES = {ControlAction.APPROVE, ControlAction.DENY}


def classify_control(text: str, *, approval_pending: bool = False) -> ControlResult | None:
    parts = tokens(text)
    if not parts:
        return None
    normalized = " ".join(parts)

    if approval_pending:
        # Asymmetric: any deny-like token in a short utterance wins.
        if len(parts) <= 5:
            for lang, deny_tokens in DENY_TOKENS.items():
                if deny_tokens.intersection(parts):
                    if normalized in _EXACT and _EXACT[normalized].action is ControlAction.STOP:
                        return _EXACT[normalized]  # explicit "stop"/"cancel"
                    return ControlResult(ControlAction.DENY, lang)
        exact = _EXACT.get(normalized)
        if exact is not None and exact.action is ControlAction.APPROVE and len(parts) <= 3:
            return exact

    exact = _EXACT.get(normalized)
    if exact is not None:
        if exact.action in _APPROVAL_CATEGORIES and not approval_pending:
            return None  # a bare "yes"/"no" with nothing pending is just speech
        return exact

    # Stop-family prefix: "stop …" / "cancel …" in <= 3 tokens.
    if len(parts) <= 3 and parts[0] in {"stop", "cancel"}:
        return ControlResult(ControlAction.STOP, "en")
    return None
