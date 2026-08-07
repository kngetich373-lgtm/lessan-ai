"""IMemoryProvider — interface every memory backend must implement.

The MemoryManager and MemoryRegistry depend *only* on this ABC. New
backends (JSON adapters today; databases / vector stores later) plug in
without changing the manager — Open/Closed compliant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from memory.models import MemoryEntry, MemoryQuery, MemorySearchHit
from memory.scopes import MemoryContext, MemoryScope


class IMemoryProvider(ABC):
    """Contract for a scoped memory backend.

    Implementations own storage for one or more :class:`MemoryScope`
    values. They must not call other providers or subsystem modules
    directly — coordination happens only through :class:`MemoryManager`.
    """

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name, e.g. ``\"long_term\"``, ``\"agent_store\"``."""

    @abstractmethod
    def supported_scopes(self) -> List[MemoryScope]:
        """Scopes this provider is willing to serve."""

    def supports_scope(self, scope: MemoryScope) -> bool:
        """Whether this provider handles ``scope``."""
        return scope in self.supported_scopes()

    # ------------------------------------------------------------------ #
    # Core CRUD
    # ------------------------------------------------------------------ #
    @abstractmethod
    def store(self, context: MemoryContext, key: str, value: Any,
              *, metadata: Optional[Dict[str, Any]] = None,
              tags: Optional[List[str]] = None) -> MemoryEntry:
        """Create or upsert an entry under ``key`` in ``context``."""

    @abstractmethod
    def retrieve(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        """Return the entry for ``key``, or None if missing / wrong scope."""

    @abstractmethod
    def update(self, context: MemoryContext, key: str, value: Any = None,
               *, metadata: Optional[Dict[str, Any]] = None,
               tags: Optional[List[str]] = None,
               patch: Optional[Dict[str, Any]] = None) -> Optional[MemoryEntry]:
        """Update an existing entry. Returns None if the key does not exist."""

    @abstractmethod
    def delete(self, context: MemoryContext, key: str) -> bool:
        """Permanently remove an entry. Returns True if it existed."""

    # ------------------------------------------------------------------ #
    # Query / lifecycle
    # ------------------------------------------------------------------ #
    @abstractmethod
    def search(self, query: MemoryQuery,
               context: Optional[MemoryContext] = None) -> List[MemorySearchHit]:
        """Search entries owned by this provider.

        ``context`` may further narrow the search; when None the provider
        uses ``query.scopes`` / ``query.scope_id`` filters.
        """

    @abstractmethod
    def summarize(self, context: MemoryContext,
                  *, limit: int = 50) -> str:
        """Return a human-readable summary of memory in ``context``."""

    @abstractmethod
    def archive(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        """Soft-retire an entry. Archived entries are excluded from default search."""

    @abstractmethod
    def restore(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        """Un-archive a previously archived entry."""

    # ------------------------------------------------------------------ #
    # Optional bulk helpers (default implementations)
    # ------------------------------------------------------------------ #
    def list_keys(self, context: MemoryContext,
                  *, include_archived: bool = False) -> List[str]:
        """Return keys visible in ``context`` (default: via empty-text search)."""
        query = MemoryQuery(
            text="",
            scopes=[context.scope],
            scope_id=context.scope_id,
            user_id=context.user_id,
            include_archived=include_archived,
            limit=10_000,
        )
        hits = self.search(query, context=context)
        return [h.entry.key for h in hits]

    def clear(self, context: MemoryContext) -> int:
        """Delete all non-archived entries in ``context``. Returns count removed."""
        removed = 0
        for key in list(self.list_keys(context, include_archived=True)):
            if self.delete(context, key):
                removed += 1
        return removed

    def info(self) -> Dict[str, Any]:
        """Provider metadata for inspection / health."""
        return {
            "name": self.name,
            "scopes": [s.value for s in self.supported_scopes()],
        }
