"""Orchestrator-facing :class:`MemoryStore` ABC adapter.

Bridges the System Orchestrator's ``core.orchestrator.interfaces.MemoryStore``
interface to :class:`~memory.manager.MemoryManager` without tight coupling.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.orchestrator.interfaces import MemoryStore as IMemoryStore


class OrchestratorMemoryStore(IMemoryStore):
    """Adapter that implements MemoryStore ABC → delegates to MemoryManager.

    The orchestrator resolves this from DI without importing concrete memory
    modules; the manager resolves providers via registry.
    """

    def __init__(self, memory_manager: Any) -> None:
        self._manager = memory_manager

    def load(self) -> Dict[str, Any]:
        from memory.scopes import MemoryContext, MemoryScope

        ctx = MemoryContext(scope=MemoryScope.USER)
        # Return flat dict from user scope for backward compat
        results = {}
        try:
            keys = self._manager.list_keys(ctx, include_archived=False)[:100]
            for key in keys:
                entry = self._manager.retrieve(ctx, key)
                if entry:
                    results[entry.key] = entry.value
        except Exception:
            pass
        return results

    def save(self, memory_update: Dict[str, Any]) -> Dict[str, Any]:
        from memory.scopes import MemoryContext, MemoryScope

        ctx = MemoryContext(scope=MemoryScope.USER)
        for key, value in (memory_update or {}).items():
            if value is not None:
                try:
                    self._manager.store(ctx, key, value)
                except Exception:
                    pass
        return self.load()

    def format_for_prompt(self, memory: Optional[Dict[str, Any]] = None) -> str:
        from memory.scopes import MemoryContext, MemoryScope

        ctx = MemoryContext(scope=MemoryScope.USER)
        try:
            return self._manager.compose_prompt([ctx], limit=100)
        except Exception:
            return ""
