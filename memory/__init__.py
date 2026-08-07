"""Unified Memory System for Lessan.

Public API
----------
- :class:`MemoryManager`: Single entry point for all memory operations
- :class:`MemoryContext`: Scope + identity for memory isolation
- :class:`MemoryScope`: Enum (GLOBAL, USER, WORKSPACE, PROJECT, WORKFLOW, AGENT, SESSION)
- :class:`MemoryEntry`: Value object for a memory record
- :func:`register_memory_system`: DI registration (call once at startup)

Legacy compatibility
--------------------
The legacy ``memory_manager`` and ``conversation_memory`` modules remain
unchanged. Adapters wrap them for backward compatibility.

Example usage
-------------
>>> from core.di import Container
>>> from memory import register_memory_system, MemoryManager, MemoryContext, MemoryScope
>>>
>>> container = Container()
>>> register_memory_system(container)
>>> manager = container.resolve(MemoryManager)
>>>
>>> ctx = MemoryContext(scope=MemoryScope.USER, user_id="alice")
>>> manager.store(ctx, "favorite_color", "blue")
>>> entry = manager.retrieve(ctx, "favorite_color")
>>> print(entry.value)  # "blue"
"""

from memory.di import register_memory_system, unregister_memory_system
from memory.events import (
    EV_MEMORY_ARCHIVED,
    EV_MEMORY_DELETED,
    EV_MEMORY_RESTORED,
    EV_MEMORY_RETRIEVED,
    EV_MEMORY_SEARCHED,
    EV_MEMORY_STORED,
    EV_MEMORY_SUMMARIZED,
    EV_MEMORY_UPDATED,
    EV_PROVIDER_REGISTERED,
    EV_PROVIDER_UNREGISTERED,
)
from memory.manager import MemoryManager
from memory.models import MemoryEntry, MemoryOperationResult, MemoryQuery, MemorySearchHit
from memory.provider import IMemoryProvider
from memory.registry import MemoryRegistry
from memory.scopes import MemoryContext, MemoryScope
from memory.search import MemorySearch

__all__ = [
    # Core API
    "MemoryManager",
    "MemoryContext",
    "MemoryScope",
    "MemoryEntry",
    "MemoryQuery",
    "MemorySearchHit",
    "MemoryOperationResult",
    # DI
    "register_memory_system",
    "unregister_memory_system",
    # Extensions
    "IMemoryProvider",
    "MemoryRegistry",
    "MemorySearch",
    # Events
    "EV_MEMORY_STORED",
    "EV_MEMORY_RETRIEVED",
    "EV_MEMORY_UPDATED",
    "EV_MEMORY_DELETED",
    "EV_MEMORY_SEARCHED",
    "EV_MEMORY_SUMMARIZED",
    "EV_MEMORY_ARCHIVED",
    "EV_MEMORY_RESTORED",
    "EV_PROVIDER_REGISTERED",
    "EV_PROVIDER_UNREGISTERED",
]
