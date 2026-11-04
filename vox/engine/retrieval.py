"""Device index + retrieval (spec 4.3): BM25 + phonetic, local only.

Chunks describe installed apps, window titles, monitors, folders and
saved aliases (names/metadata only — file *contents* are never indexed).
Vector retrieval is intentionally absent: no licence-verified local
embedding model is available in this environment, and the spec's Tier-A
fallback is exactly BM25 + phonetic fuzzy match (recorded in DECISIONS).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from vox.engine.glossary import Glossary, phonetic_key, words

ChunkSource = Literal["app", "window", "folder", "monitor", "alias", "preference"]


@dataclass(frozen=True)
class Chunk:
    id: str
    source: ChunkSource
    title: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class DeviceIndex:
    """In-memory index, refreshed incrementally off the critical path."""

    def __init__(self, glossary: Glossary | None = None) -> None:
        self._glossary = glossary if glossary is not None else Glossary()
        self._chunks: dict[str, Chunk] = {}
        self._tokens: dict[str, Counter[str]] = {}
        self._sequence = 0

    # -- population -----------------------------------------------------------

    def _add(self, source: ChunkSource, title: str, text: str, data: dict[str, Any]) -> Chunk:
        self._sequence += 1
        chunk = Chunk(
            id=f"{source}-{self._sequence}", source=source, title=title, text=text, data=data
        )
        self._chunks[chunk.id] = chunk
        self._tokens[chunk.id] = Counter(words(f"{title} {text}"))
        return chunk

    def index_apps(self, names: list[str]) -> None:
        variants = {entry.canonical: " ".join(entry.variants) for entry in self._glossary.entries}
        for name in names:
            self._add("app", name, variants.get(name, ""), {"name": name})

    def index_windows(self, titles: list[str]) -> None:
        for title in titles:
            self._add("window", title, "", {"title": title})

    def index_monitors(self, labels: list[str]) -> None:
        for label in labels:
            self._add("monitor", label, "", {"label": label})

    def index_folders(self, named: dict[str, str]) -> None:
        for name, path in named.items():
            self._add("folder", name, path, {"path": path})

    def index_aliases(self, aliases: dict[str, str]) -> None:
        for alias, target in aliases.items():
            self._add("alias", alias, target, {"target": target})

    def remove_source(self, source: ChunkSource) -> None:
        for chunk_id in [cid for cid, c in self._chunks.items() if c.source == source]:
            del self._chunks[chunk_id]
            del self._tokens[chunk_id]

    def __len__(self) -> int:
        return len(self._chunks)

    # -- search -----------------------------------------------------------------

    def search(
        self, query: str, *, k: int = 6, source: ChunkSource | None = None
    ) -> list[ScoredChunk]:
        query_tokens = words(query)
        if not query_tokens or not self._chunks:
            return []
        candidates = [c for c in self._chunks.values() if source is None or c.source == source]
        if not candidates:
            return []
        doc_freq: Counter[str] = Counter()
        for chunk in candidates:
            doc_freq.update(self._tokens[chunk.id].keys())
        avg_len = sum(sum(self._tokens[c.id].values()) for c in candidates) / len(candidates)
        total = len(candidates)
        query_keys = {phonetic_key(token) for token in query_tokens}
        scored: list[ScoredChunk] = []
        for chunk in candidates:
            counts = self._tokens[chunk.id]
            length = max(1, sum(counts.values()))
            score = 0.0
            for token in query_tokens:
                tf = counts.get(token, 0)
                if tf:
                    idf = math.log(1 + (total - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
                    score += (
                        idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / max(1.0, avg_len)))
                    )
            title_tokens = words(chunk.title)
            if title_tokens == query_tokens:
                score += 3.0  # exact title match dominates
            if query_keys & {phonetic_key(token) for token in counts} - {
                phonetic_key(token) for token in query_tokens if counts.get(token)
            }:
                score += 0.75  # sound-alike but not literal token present
            if score > 0:
                scored.append(ScoredChunk(chunk=chunk, score=round(score, 4)))
        scored.sort(key=lambda item: (-item.score, item.chunk.id))
        return scored[:k]

    # -- app helpers (edge case 11: honest absence) ------------------------------

    def find_app(self, name: str) -> Chunk | None:
        wanted = " ".join(words(name))
        for chunk in self._chunks.values():
            if chunk.source == "app" and " ".join(words(chunk.title)) == wanted:
                return chunk
        return None

    def nearest_apps(self, name: str, *, k: int = 3) -> list[str]:
        return [hit.chunk.title for hit in self.search(name, k=k, source="app")]
