"""Memory scope definitions for the Unified Memory System.

Scopes isolate memory while allowing controlled sharing through
:class:`~memory.manager.MemoryManager` multi-scope APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryScope(str, Enum):
    """Logical isolation boundary for memory entries."""

    GLOBAL = "global"
    USER = "user"
    WORKSPACE = "workspace"
    PROJECT = "project"
    WORKFLOW = "workflow"
    AGENT = "agent"
    SESSION = "session"


@dataclass(frozen=True)
class MemoryContext:
    """Identifies where a memory operation applies.

    Attributes:
        scope: The isolation boundary.
        scope_id: Optional instance id within the scope
            (e.g. agent name, workspace name, workflow id, session id).
        user_id: Optional user identity for multi-user isolation.
        tags: Optional free-form tags for filtering.
    """

    scope: MemoryScope
    scope_id: Optional[str] = None
    user_id: Optional[str] = None
    tags: tuple = field(default_factory=tuple)

    def namespace_key(self, key: str) -> str:
        """Build a fully-qualified key that cannot collide across scopes."""
        parts = [self.scope.value]
        if self.user_id:
            parts.append(f"u:{self.user_id}")
        if self.scope_id:
            parts.append(self.scope_id)
        parts.append(key)
        return "/".join(parts)

    def matches_tags(self, entry_tags: Optional[List[str]]) -> bool:
        """Return True if this context's tags are a subset of entry tags."""
        if not self.tags:
            return True
        entry = set(entry_tags or ())
        return set(self.tags).issubset(entry)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope.value,
            "scope_id": self.scope_id,
            "user_id": self.user_id,
            "tags": list(self.tags),
        }
