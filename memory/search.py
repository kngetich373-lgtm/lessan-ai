"""MemorySearch — multi-provider keyword search for the Unified Memory System.

Fans out queries to registered providers, merges results, and ranks by
relevance (exact key > substring > recency). Vector search will be added
later behind the same interface.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from memory.models import MemoryQuery, MemorySearchHit
from memory.registry import MemoryRegistry


class MemorySearch:
    """Coordinates search across multiple memory providers."""

    def __init__(self, registry: MemoryRegistry) -> None:
        self._registry = registry

    def search(self, query: MemoryQuery) -> List[MemorySearchHit]:
        """Execute a search across relevant providers.

        Providers are chosen by:
          1. query.provider_names (explicit list)
          2. query.scopes → providers for those scopes
          3. all providers if neither specified
        """
        providers = self._select_providers(query)
        all_hits: List[MemorySearchHit] = []

        for provider in providers:
            try:
                hits = provider.search(query)
                all_hits.extend(hits)
            except Exception:
                # Keep search resilient; one provider failure doesn't fail all
                pass

        # Re-sort merged results by score then updated_at
        all_hits.sort(key=lambda h: (-h.score, h.entry.updated_at or ""))
        return all_hits[: max(1, query.limit)]

    def count(self, query: MemoryQuery) -> int:
        """Return the count of matching entries without full results."""
        query = MemoryQuery(
            text=query.text,
            scopes=query.scopes,
            scope_id=query.scope_id,
            user_id=query.user_id,
            tags=query.tags,
            key_prefix=query.key_prefix,
            include_archived=query.include_archived,
            limit=10_000,
            provider_names=query.provider_names,
        )
        hits = self.search(query)
        return len(hits)

    def _select_providers(self, query: MemoryQuery) -> list:
        if query.provider_names:
            providers = []
            for name in query.provider_names:
                p = self._registry.get(name)
                if p is not None:
                    providers.append(p)
            return providers

        if query.scopes:
            matched = set()
            for scope in query.scopes:
                matched.update(self._registry.for_scope(scope))
            return list(matched)

        return self._registry.all()
