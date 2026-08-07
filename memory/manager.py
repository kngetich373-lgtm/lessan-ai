"""MemoryManager — single entry point for the Unified Memory System.

Coordinates all memory operations across scopes, providers, and subsystems.
Subsystems (orchestrator, agents, workflows, workspaces) resolve this via DI.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from core.logging import get_logger

from memory.events import (
    EV_MEMORY_ARCHIVED,
    EV_MEMORY_DELETED,
    EV_MEMORY_RESTORED,
    EV_MEMORY_RETRIEVED,
    EV_MEMORY_SEARCHED,
    EV_MEMORY_STORED,
    EV_MEMORY_SUMMARIZED,
    EV_MEMORY_UPDATED,
    emit_memory_event,
)
from memory.models import MemoryEntry, MemoryOperationResult, MemoryQuery
from memory.provider import IMemoryProvider
from memory.registry import MemoryRegistry
from memory.scopes import MemoryContext, MemoryScope

logger = get_logger("memory.manager")


class MemoryManager:
    """Facade over the memory registry and providers.

    The manager enforces scope isolation while enabling controlled sharing
    through multi-scope APIs (search, compose_prompt). It publishes events
    after mutations and optionally mirrors meta counts into StateStore.
    """

    def __init__(
        self,
        registry: MemoryRegistry,
        event_bus: Any = None,
        state_store: Any = None,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._state = state_store
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Core CRUD
    # ------------------------------------------------------------------ #
    def store(
        self,
        context: MemoryContext,
        key: str,
        value: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> MemoryEntry:
        """Create or upsert a memory entry."""
        provider = self._resolve_provider(context.scope, "store")
        entry = provider.store(context, key, value, metadata=metadata, tags=tags)
        emit_memory_event(
            EV_MEMORY_STORED,
            self._entry_payload(entry, operation="store"),
            bus=self._event_bus,
        )
        self._update_meta_counts()
        return entry

    def retrieve(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        """Retrieve an entry by key."""
        provider = self._resolve_provider(context.scope, "retrieve")
        entry = provider.retrieve(context, key)
        if entry is not None:
            emit_memory_event(
                EV_MEMORY_RETRIEVED,
                self._entry_payload(entry, operation="retrieve"),
                bus=self._event_bus,
            )
        return entry

    def update(
        self,
        context: MemoryContext,
        key: str,
        value: Any = None,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        patch: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryEntry]:
        """Update an existing entry."""
        provider = self._resolve_provider(context.scope, "update")
        entry = provider.update(
            context, key, value, metadata=metadata, tags=tags, patch=patch
        )
        if entry is not None:
            emit_memory_event(
                EV_MEMORY_UPDATED,
                self._entry_payload(entry, operation="update"),
                bus=self._event_bus,
            )
        return entry

    def delete(self, context: MemoryContext, key: str) -> bool:
        """Delete an entry."""
        provider = self._resolve_provider(context.scope, "delete")
        removed = provider.delete(context, key)
        if removed:
            emit_memory_event(
                EV_MEMORY_DELETED,
                {
                    "scope": context.scope.value,
                    "scope_id": context.scope_id,
                    "user_id": context.user_id,
                    "key": key,
                    "provider": provider.name,
                },
                bus=self._event_bus,
            )
            self._update_meta_counts()
        return removed

    # ------------------------------------------------------------------ #
    # Search & lifecycle
    # ------------------------------------------------------------------ #
    def search(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search across providers matching query scopes/filters."""
        from memory.search import MemorySearch

        search_svc = MemorySearch(self._registry)
        hits = search_svc.search(query)
        emit_memory_event(
            EV_MEMORY_SEARCHED,
            {"query": query.as_dict(), "count": len(hits)},
            bus=self._event_bus,
        )
        return [h.entry for h in hits]

    def summarize(self, context: MemoryContext, *, limit: int = 50) -> str:
        """Generate a human-readable summary for a context."""
        provider = self._resolve_provider(context.scope, "summarize")
        summary = provider.summarize(context, limit=limit)
        emit_memory_event(
            EV_MEMORY_SUMMARIZED,
            {
                "scope": context.scope.value,
                "scope_id": context.scope_id,
                "length": len(summary),
            },
            bus=self._event_bus,
        )
        return summary

    def archive(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        """Soft-retire an entry."""
        provider = self._resolve_provider(context.scope, "archive")
        entry = provider.archive(context, key)
        if entry is not None:
            emit_memory_event(
                EV_MEMORY_ARCHIVED,
                self._entry_payload(entry, operation="archive"),
                bus=self._event_bus,
            )
        return entry

    def restore(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        """Un-archive an entry."""
        provider = self._resolve_provider(context.scope, "restore")
        entry = provider.restore(context, key)
        if entry is not None:
            emit_memory_event(
                EV_MEMORY_RESTORED,
                self._entry_payload(entry, operation="restore"),
                bus=self._event_bus,
            )
        return entry

    # ------------------------------------------------------------------ #
    # Bulk / convenience
    # ------------------------------------------------------------------ #
    def list_keys(
        self, context: MemoryContext, *, include_archived: bool = False
    ) -> List[str]:
        """List keys in a context."""
        provider = self._resolve_provider(context.scope, "list_keys")
        return provider.list_keys(context, include_archived=include_archived)

    def clear(self, context: MemoryContext) -> int:
        """Clear all entries in a context. Returns count removed."""
        provider = self._resolve_provider(context.scope, "clear")
        removed = provider.clear(context)
        self._update_meta_counts()
        return removed

    # ------------------------------------------------------------------ #
    # Multi-scope controlled sharing
    # ------------------------------------------------------------------ #
    def compose_prompt(
        self, contexts: List[MemoryContext], *, limit: int = 50
    ) -> str:
        """Compose a multi-scope memory block for prompt injection.

        Example: [USER, SESSION, WORKSPACE] → unified summary.
        """
        blocks: List[str] = []
        for ctx in contexts:
            provider = self._resolve_provider(ctx.scope, "summarize", raise_on_missing=False)
            if provider is None:
                continue
            try:
                block = provider.summarize(ctx, limit=limit)
                if block:
                    blocks.append(block)
            except Exception as exc:
                logger.warning(
                    f"Summarize failed for {ctx.scope.value}/{ctx.scope_id}: {exc}"
                )
        return "\n\n".join(blocks)

    def search_multi(
        self,
        text: str,
        scopes: List[MemoryScope],
        *,
        scope_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """Search across multiple scopes."""
        query = MemoryQuery(
            text=text,
            scopes=scopes,
            scope_id=scope_id,
            user_id=user_id,
            limit=limit,
        )
        return self.search(query)

    # ------------------------------------------------------------------ #
    # Introspection / health
    # ------------------------------------------------------------------ #
    def available_scopes(self) -> List[MemoryScope]:
        """Return scopes covered by at least one provider."""
        scopes = set()
        for provider in self._registry.all():
            scopes.update(provider.supported_scopes())
        return sorted(scopes, key=lambda s: s.value)

    def provider_names(self) -> List[str]:
        """Return registered provider names."""
        return self._registry.names()

    def info(self) -> Dict[str, Any]:
        """Manager + registry status."""
        return {
            "providers": len(self._registry),
            "scopes": [s.value for s in self.available_scopes()],
            "provider_list": [
                {"name": p.name, "scopes": [s.value for s in p.supported_scopes()]}
                for p in self._registry.all()
            ],
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _resolve_provider(
        self, scope: MemoryScope, operation: str, raise_on_missing: bool = True
    ) -> Optional[IMemoryProvider]:
        """Select the primary provider for a scope."""
        provider = self._registry.primary_for_scope(scope)
        if provider is None and raise_on_missing:
            raise ValueError(
                f"No memory provider registered for scope '{scope.value}' (operation: {operation})"
            )
        return provider

    @staticmethod
    def _entry_payload(entry: MemoryEntry, operation: str) -> Dict[str, Any]:
        return {
            "operation": operation,
            "scope": entry.context.scope.value,
            "scope_id": entry.context.scope_id,
            "user_id": entry.context.user_id,
            "key": entry.key,
            "provider": entry.provider,
            "entry_id": entry.entry_id,
        }

    def _update_meta_counts(self) -> None:
        """Optionally mirror high-level counts into StateStore (non-blocking)."""
        if self._state is None:
            return
        try:
            counts = {}
            for scope in self.available_scopes():
                providers = self._registry.for_scope(scope)
                counts[scope.value] = len(providers)
            with self._lock:
                if hasattr(self._state, "update"):
                    self._state.update("memory.meta", {"provider_counts": counts})
        except Exception:
            pass
