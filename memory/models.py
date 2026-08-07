"""Value objects for the Unified Memory System.

Provider-neutral models so the MemoryManager never depends on a concrete
storage backend. Databases and vector stores can be added later behind
:class:`~memory.provider.IMemoryProvider` without changing these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from memory.scopes import MemoryContext, MemoryScope


@dataclass
class MemoryEntry:
    """A single memory record."""

    key: str
    value: Any
    context: MemoryContext
    entry_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived: bool = False
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
        if self.entry_id is None:
            self.entry_id = self.context.namespace_key(self.key)

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "key": self.key,
            "value": self.value,
            "context": self.context.as_dict(),
            "metadata": dict(self.metadata),
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived": self.archived,
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        ctx_data = data.get("context") or {}
        scope_raw = ctx_data.get("scope", MemoryScope.SESSION.value)
        try:
            scope = MemoryScope(scope_raw)
        except ValueError:
            scope = MemoryScope.SESSION
        context = MemoryContext(
            scope=scope,
            scope_id=ctx_data.get("scope_id"),
            user_id=ctx_data.get("user_id"),
            tags=tuple(ctx_data.get("tags") or ()),
        )
        return cls(
            key=str(data.get("key", "")),
            value=data.get("value"),
            context=context,
            entry_id=data.get("entry_id"),
            metadata=dict(data.get("metadata") or {}),
            tags=list(data.get("tags") or []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            archived=bool(data.get("archived", False)),
            provider=data.get("provider"),
        )


@dataclass
class MemoryQuery:
    """Search / filter request for :class:`~memory.search.MemorySearch`."""

    text: str = ""
    scopes: Optional[List[MemoryScope]] = None
    scope_id: Optional[str] = None
    user_id: Optional[str] = None
    tags: Optional[List[str]] = None
    key_prefix: Optional[str] = None
    include_archived: bool = False
    limit: int = 50
    provider_names: Optional[List[str]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "scopes": [s.value for s in self.scopes] if self.scopes else None,
            "scope_id": self.scope_id,
            "user_id": self.user_id,
            "tags": list(self.tags) if self.tags else None,
            "key_prefix": self.key_prefix,
            "include_archived": self.include_archived,
            "limit": self.limit,
            "provider_names": list(self.provider_names) if self.provider_names else None,
        }


@dataclass
class MemorySearchHit:
    """One ranked search result."""

    entry: MemoryEntry
    score: float = 0.0
    matched_on: str = ""  # "key" | "value" | "tag" | "metadata"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry.as_dict(),
            "score": self.score,
            "matched_on": self.matched_on,
        }


@dataclass
class MemoryOperationResult:
    """Outcome of a single memory mutation or read."""

    success: bool
    operation: str
    entry: Optional[MemoryEntry] = None
    entries: List[MemoryEntry] = field(default_factory=list)
    message: str = ""
    provider: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "entry": self.entry.as_dict() if self.entry else None,
            "entries": [e.as_dict() for e in self.entries],
            "message": self.message,
            "provider": self.provider,
        }
