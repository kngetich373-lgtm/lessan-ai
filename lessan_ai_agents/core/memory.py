"""
Agent Memory interface.

Separate from the framework's own persistent-memory product feature —
this is a per-agent scratch/long-term store an agent can use to keep
track of project context, prior decisions, etc. Kept as a narrow
Protocol so any backing store (in-memory dict, SQLite, vector DB) can
implement it without the agent code caring which one it got.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol, runtime_checkable


@dataclass
class MemoryRecord:
    """A single stored memory entry."""

    key: str
    value: Any
    tags: tuple = field(default_factory=tuple)
    stored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class IAgentMemory(Protocol):
    """Storage contract for agent memory. Intentionally minimal (CRUD +
    a tag-based query) so alternative backends stay easy to write."""

    def remember(self, key: str, value: Any, tags: Iterable[str] = ()) -> MemoryRecord: ...

    def recall(self, key: str) -> Optional[MemoryRecord]: ...

    def forget(self, key: str) -> bool: ...

    def query_by_tag(self, tag: str) -> list[MemoryRecord]: ...

    def all_records(self) -> list[MemoryRecord]: ...


class InMemoryAgentMemory:
    """Default, dependency-free implementation of IAgentMemory.

    Suitable for tests and single-process use. Swap in a persistent
    implementation (e.g. backed by a database) by constructing it
    behind the same IAgentMemory interface — no BaseAgent changes
    required, per the Dependency Inversion principle.
    """

    def __init__(self) -> None:
        self._store: dict[str, MemoryRecord] = {}

    def remember(self, key: str, value: Any, tags: Iterable[str] = ()) -> MemoryRecord:
        record = MemoryRecord(key=key, value=value, tags=tuple(tags))
        self._store[key] = record
        return record

    def recall(self, key: str) -> Optional[MemoryRecord]:
        return self._store.get(key)

    def forget(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def query_by_tag(self, tag: str) -> list[MemoryRecord]:
        return [r for r in self._store.values() if tag in r.tags]

    def all_records(self) -> list[MemoryRecord]:
        return list(self._store.values())
