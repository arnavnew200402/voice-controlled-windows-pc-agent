"""Memory layers (spec 4.3): user card, preferences, session store.

Persistence policy (L-03): the SQLite store keeps tool-level audit records
always; transcript *text* (user/assistant turns, wake snippets) is written
only when the user opted in via ``store_transcripts``. Raw audio is never
stored anywhere. Pending approvals are never persisted — after a crash
they are expired by construction (edge case 21).
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import vox.events as event_module
from vox.engine.entities import Entity
from vox.engine.ledger import ActionRecord
from vox.engine.timeline import TimelineEvent
from vox.events import Event


def session_dir() -> Path:
    override = os.environ.get("VOX_SESSION_DIR")
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "vox" / "session"
    return Path.home() / ".local" / "share" / "vox" / "session"


def approx_tokens(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass
class UserCard:
    name: str = ""
    languages: tuple[str, ...] = ("en",)
    pinned_language: str | None = None
    assistant_name: str = "Vox"
    verbosity: Literal["silent", "brief", "normal"] = "brief"
    confirmation_style: Literal["speech", "hud", "silent"] = "speech"
    default_browser: str = ""
    search_engine: str = ""
    monitor_layout: str = ""

    def render(self) -> str:
        lines = [
            f"User: {self.name or 'unknown'}",
            f"Languages: {', '.join(self.languages)}"
            + (f" (pinned: {self.pinned_language})" if self.pinned_language else ""),
            f"Wake: Hi {self.assistant_name} / Hey {self.assistant_name}",
            f"Style: verbosity={self.verbosity}, confirmations={self.confirmation_style}",
        ]
        if self.default_browser:
            lines.append(f"Default browser: {self.default_browser}")
        if self.search_engine:
            lines.append(f"Search: {self.search_engine}")
        if self.monitor_layout:
            lines.append(f"Monitors: {self.monitor_layout}")
        return "\n".join(lines)

    def save(self, directory: Path | None = None) -> Path:
        path = (directory or session_dir()) / "user_card.json"
        _write_json(path, asdict(self))
        return path

    @classmethod
    def load(cls, directory: Path | None = None) -> UserCard:
        data = _read_json((directory or session_dir()) / "user_card.json")
        known = {name for name in cls.__dataclass_fields__}
        filtered = {key: value for key, value in data.items() if key in known}
        if isinstance(filtered.get("languages"), list):
            filtered["languages"] = tuple(filtered["languages"])
        return cls(**filtered)


@dataclass
class PreferencesSheet:
    named_locations: dict[str, str] = field(default_factory=dict)
    default_apps: dict[str, str] = field(default_factory=dict)
    monitor_per_app: dict[str, str] = field(default_factory=dict)
    units: str = "metric"
    time_format: str = "24h"
    do_not_touch: tuple[str, ...] = ()

    def resolve_location(self, name: str) -> str | None:
        lowered = name.strip().lower()
        for key, value in self.named_locations.items():
            if key.lower() == lowered:
                return value
        return None

    def render(self) -> str:
        lines: list[str] = []
        for key, value in sorted(self.named_locations.items()):
            lines.append(f"{key}: {value}")
        for key, value in sorted(self.default_apps.items()):
            lines.append(f"default {key}: {value}")
        for key, value in sorted(self.monitor_per_app.items()):
            lines.append(f"{key} on: {value}")
        lines.append(f"Units: {self.units}; time: {self.time_format}")
        if self.do_not_touch:
            lines.append("Do not touch: " + ", ".join(self.do_not_touch))
        return "\n".join(lines)

    def save(self, directory: Path | None = None) -> Path:
        path = (directory or session_dir()) / "preferences.json"
        _write_json(path, asdict(self))
        return path

    @classmethod
    def load(cls, directory: Path | None = None) -> PreferencesSheet:
        data = _read_json((directory or session_dir()) / "preferences.json")
        known = {name for name in cls.__dataclass_fields__}
        filtered = {key: value for key, value in data.items() if key in known}
        if isinstance(filtered.get("do_not_touch"), list):
            filtered["do_not_touch"] = tuple(filtered["do_not_touch"])
        return cls(**filtered)


@dataclass
class HabitProposal:
    key: str
    value: str
    evidence_turns: tuple[str, ...] = ()


class SessionMemory:
    """Session-scoped memory (rolling summary, habits, open tasks).

    Habits follow L-08: learned preferences are proposals until confirmed.
    Background writers (summary refresh) land in LE5; LE3 provides the
    structures and explicit, testable mutation rules.
    """

    def __init__(self) -> None:
        self.rolling_summary = ""
        self.open_tasks: list[str] = []
        self._habits: dict[str, str] = {}
        self._proposals: dict[str, HabitProposal] = {}

    def propose_habit(self, key: str, value: str, turn_id: str = "") -> None:
        if key not in self._habits:
            self._proposals[key] = HabitProposal(key, value, (turn_id,) if turn_id else ())

    def habit_proposals(self) -> list[HabitProposal]:
        return list(self._proposals.values())

    def confirm_habit(self, key: str) -> bool:
        proposal = self._proposals.pop(key, None)
        if proposal is None:
            return False
        self._habits[key] = proposal.value
        return True

    def habits(self) -> dict[str, str]:
        return dict(self._habits)


# -- SQLite session store ------------------------------------------------------

_AUDIT_EVENT_TYPES = {"tool_started", "tool_finished", "approval_requested", "approval_resolved"}

_EVENT_CLASSES: dict[str, type[Event]] = {}
for _name in dir(event_module):
    _candidate = getattr(event_module, _name)
    if isinstance(_candidate, type) and issubclass(_candidate, Event) and _candidate is not Event:
        _EVENT_CLASSES[str(_candidate.model_fields["type"].default)] = _candidate


@dataclass
class RestoredSession:
    timeline: list[TimelineEvent]
    actions: list[ActionRecord]
    entities: list[Entity]
    unknown_tools: list[str]  # tool_started without tool_finished (verify, never re-run)
    pending_approvals: tuple[()] = ()  # never persisted: always expired


class SessionStore:
    def __init__(self, directory: Path | None = None, *, store_transcripts: bool = False) -> None:
        self._dir = directory or session_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._store_transcripts = store_transcripts
        self._conn = sqlite3.connect(self._dir / "session.db")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS timeline (
              id INTEGER PRIMARY KEY, turn_id TEXT, t_mono REAL, t_wall REAL,
              speaker TEXT, kind TEXT, text TEXT, asr_confidence REAL,
              lang TEXT, event_type TEXT, event_json TEXT);
            CREATE TABLE IF NOT EXISTS actions (
              action_id TEXT PRIMARY KEY, turn_id TEXT, tool TEXT, ok INTEGER,
              evidence TEXT, target_label TEXT, args_json TEXT, undo_json TEXT,
              t_wall REAL, undone INTEGER);
            CREATE TABLE IF NOT EXISTS entities (
              id TEXT PRIMARY KEY, kind TEXT, label TEXT, data_json TEXT,
              registered_at REAL, ttl_s REAL);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- writes ---------------------------------------------------------------

    def checkpoint_timeline(self, events: Iterable[TimelineEvent]) -> None:
        rows = []
        for event in events:
            keep_text = self._store_transcripts or event.speaker == "tool"
            event_type = str(event.event.type) if event.event is not None else None
            store_payload = event.event is not None and (
                self._store_transcripts or event_type in _AUDIT_EVENT_TYPES
            )
            rows.append(
                (
                    event.id,
                    event.turn_id,
                    event.t_mono,
                    event.t_wall,
                    event.speaker,
                    event.kind,
                    event.text if keep_text else "",
                    event.asr_confidence,
                    event.lang,
                    event_type,
                    event.event.model_dump_json() if store_payload else None,
                )
            )
        self._conn.executemany(
            "INSERT OR REPLACE INTO timeline VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        self._conn.commit()

    def append_action(self, record: ActionRecord) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                record.action_id,
                record.turn_id,
                record.tool,
                1 if record.ok else 0,
                record.evidence,
                record.target_label,
                json.dumps(record.args_redacted, ensure_ascii=False),
                json.dumps(record.undo_info, ensure_ascii=False)
                if record.undo_info is not None
                else None,
                record.t_wall,
                1 if record.undone else 0,
            ),
        )
        self._conn.commit()

    def snapshot_entities(self, entities: Iterable[Entity]) -> None:
        self._conn.execute("DELETE FROM entities")
        self._conn.executemany(
            "INSERT INTO entities VALUES (?,?,?,?,?,?)",
            [
                (
                    entity.id,
                    entity.kind,
                    entity.label,
                    json.dumps(entity.data, ensure_ascii=False),
                    entity.registered_at,
                    entity.ttl_s,
                )
                for entity in entities
            ],
        )
        self._conn.commit()

    # -- restore --------------------------------------------------------------

    def _restore_event(self, payload: str | None) -> Event | None:
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
            cls = _EVENT_CLASSES.get(str(parsed.get("type")))
            return cls.model_validate(parsed) if cls is not None else None
        except (ValueError, AttributeError):
            return None

    def restore(self) -> RestoredSession:
        timeline: list[TimelineEvent] = []
        in_flight: dict[str, int] = {}
        for row in self._conn.execute("SELECT * FROM timeline ORDER BY id"):
            event = self._restore_event(row[10])
            timeline.append(
                TimelineEvent(
                    id=int(row[0]),
                    turn_id=row[1],
                    t_mono=float(row[2]),
                    t_wall=float(row[3]),
                    speaker=row[4],  # type: ignore[arg-type]
                    kind=row[5],  # type: ignore[arg-type]
                    text=str(row[6] or ""),
                    asr_confidence=row[7],
                    lang=row[8],
                    event=event,
                )
            )
            if row[9] == "tool_started" and event is not None:
                name = str(getattr(event, "name", ""))
                in_flight[name] = in_flight.get(name, 0) + 1
            elif row[9] == "tool_finished" and event is not None:
                name = str(getattr(event, "name", ""))
                in_flight[name] = in_flight.get(name, 0) - 1
        unknown = sorted(name for name, count in in_flight.items() if count > 0)

        actions = [
            ActionRecord(
                action_id=str(row[0]),
                turn_id=str(row[1]),
                tool=str(row[2]),
                ok=bool(row[3]),
                evidence=str(row[4]),
                target_label=str(row[5]),
                args_redacted=json.loads(row[6]) if row[6] else {},
                undo_info=json.loads(row[7]) if row[7] else None,
                t_wall=float(row[8]),
                undone=bool(row[9]),
            )
            for row in self._conn.execute("SELECT * FROM actions ORDER BY t_wall, action_id")
        ]
        entities = [
            Entity(
                id=str(row[0]),
                kind=row[1],  # type: ignore[arg-type]
                label=str(row[2]),
                data=json.loads(row[3]) if row[3] else {},
                registered_at=float(row[4]),
                ttl_s=float(row[5]),
            )
            for row in self._conn.execute("SELECT * FROM entities")
        ]
        return RestoredSession(
            timeline=timeline, actions=actions, entities=entities, unknown_tools=unknown
        )

    # -- deletion / diagnostics ------------------------------------------------

    def delete_session_data(self) -> None:
        """Wipe session data (timeline, actions, entities). Profile files
        (user card / preferences) are separate and intentionally kept."""
        for table in ("timeline", "actions", "entities"):
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()
        self._conn.execute("VACUUM")

    def counts(self) -> dict[str, int]:
        return {
            table: int(self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("timeline", "actions", "entities")
        }
