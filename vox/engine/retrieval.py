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
        self._postings: dict[str, set[str]] = {}
        self._phonetic_postings: dict[str, set[str]] = {}
        self._doc_freq: Counter[str] = Counter()
        self._total_tokens = 0
        self._title_tokens: dict[str, list[str]] = {}
        self._phonetic_keys: dict[str, set[str]] = {}
        self._sequence = 0

    # -- population -----------------------------------------------------------

    def _add(self, source: ChunkSource, title: str, text: str, data: dict[str, Any]) -> Chunk:
        self._sequence += 1
        chunk = Chunk(
            id=f"{source}-{self._sequence}", source=source, title=title, text=text, data=data
        )
        self._chunks[chunk.id] = chunk
        counts = Counter(words(f"{title} {text}"))
        self._tokens[chunk.id] = counts
        self._title_tokens[chunk.id] = words(title)
        self._phonetic_keys[chunk.id] = {phonetic_key(token) for token in counts}
        self._total_tokens += sum(counts.values())
        for token in counts:
            self._postings.setdefault(token, set()).add(chunk.id)
            self._phonetic_postings.setdefault(phonetic_key(token), set()).add(chunk.id)
            self._doc_freq[token] += 1
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
            counts = self._tokens.pop(chunk_id)
            self._title_tokens.pop(chunk_id)
            self._phonetic_keys.pop(chunk_id)
            self._total_tokens -= sum(counts.values())
            for token in counts:
                self._postings[token].discard(chunk_id)
                self._phonetic_postings[phonetic_key(token)].discard(chunk_id)
                self._doc_freq[token] -= 1
            del self._chunks[chunk_id]

    def __len__(self) -> int:
        return len(self._chunks)

    # -- search -----------------------------------------------------------------

    def search(
        self, query: str, *, k: int = 6, source: ChunkSource | None = None
    ) -> list[ScoredChunk]:
        query_tokens = words(query)
        if not query_tokens or not self._chunks:
            return []
        # Inverted index: only chunks sharing a token (or a phonetic key)
        # with the query are ever scored — O(postings), not O(index).
        candidate_ids: set[str] = set()
        for token in query_tokens:
            candidate_ids |= self._postings.get(token, set())
            candidate_ids |= self._phonetic_postings.get(phonetic_key(token), set())
        candidates = [
            self._chunks[chunk_id]
            for chunk_id in candidate_ids
            if source is None or self._chunks[chunk_id].source == source
        ]
        if not candidates:
            return []
        total = len(self._chunks)
        avg_len = self._total_tokens / total
        query_literal_keys = {
            phonetic_key(token) for token in query_tokens if self._postings.get(token)
        }
        query_all_keys = {phonetic_key(token) for token in query_tokens}
        scored: list[ScoredChunk] = []
        for chunk in candidates:
            counts = self._tokens[chunk.id]
            length = max(1, sum(counts.values()))
            score = 0.0
            for token in query_tokens:
                tf = counts.get(token, 0)
                if tf:
                    df = self._doc_freq[token]
                    idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                    score += (
                        idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / max(1.0, avg_len)))
                    )
            if self._title_tokens[chunk.id] == query_tokens:
                score += 3.0  # exact title match dominates
            elif self._phonetic_keys[chunk.id] & query_all_keys - query_literal_keys:
                score += 0.75  # sound-alike but not a literal token present
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
