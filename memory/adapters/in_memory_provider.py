"""Generic in-memory :class:`IMemoryProvider` for scoped stores.

Used for AGENT, WORKSPACE, PROJECT, WORKFLOW, and ephemeral SESSION keys.
No database — pure process-local dict storage. Thread-safe.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence

from memory.models import MemoryEntry, MemoryQuery, MemorySearchHit
from memory.provider import IMemoryProvider
from memory.scopes import MemoryContext, MemoryScope


class InMemoryProvider(IMemoryProvider):
    """Dict-backed provider for one or more scopes."""

    def __init__(
        self,
        name: str = "in_memory",
        scopes: Optional[Sequence[MemoryScope]] = None,
    ) -> None:
        self._name = name
        self._scopes = list(
            scopes
            or (
                MemoryScope.AGENT,
                MemoryScope.WORKSPACE,
                MemoryScope.PROJECT,
                MemoryScope.WORKFLOW,
                MemoryScope.SESSION,
                MemoryScope.GLOBAL,
            )
        )
        self._store: Dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return self._name

    def supported_scopes(self) -> List[MemoryScope]:
        return list(self._scopes)

    def store(
        self,
        context: MemoryContext,
        key: str,
        value: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> MemoryEntry:
        self._assert_scope(context)
        ns = context.namespace_key(key)
        with self._lock:
            existing = self._store.get(ns)
            if existing is not None:
                existing.value = deepcopy(value)
                if metadata is not None:
                    existing.metadata.update(deepcopy(metadata))
                if tags is not None:
                    existing.tags = list(tags)
                existing.archived = False
                existing.touch()
                existing.provider = self._name
                return deepcopy(existing)

            entry = MemoryEntry(
                key=key,
                value=deepcopy(value),
                context=context,
                metadata=deepcopy(metadata or {}),
                tags=list(tags or []),
                provider=self._name,
            )
            self._store[ns] = entry
            return deepcopy(entry)

    def retrieve(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        self._assert_scope(context)
        ns = context.namespace_key(key)
        with self._lock:
            entry = self._store.get(ns)
            return deepcopy(entry) if entry is not None else None

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
        self._assert_scope(context)
        ns = context.namespace_key(key)
        with self._lock:
            entry = self._store.get(ns)
            if entry is None:
                return None
            if value is not None:
                entry.value = deepcopy(value)
            if metadata is not None:
                entry.metadata.update(deepcopy(metadata))
            if tags is not None:
                entry.tags = list(tags)
            if patch and isinstance(entry.value, dict) and isinstance(patch, dict):
                entry.value = {**entry.value, **deepcopy(patch)}
            entry.touch()
            entry.provider = self._name
            return deepcopy(entry)

    def delete(self, context: MemoryContext, key: str) -> bool:
        self._assert_scope(context)
        ns = context.namespace_key(key)
        with self._lock:
            return self._store.pop(ns, None) is not None

    # ------------------------------------------------------------------ #
    # Search / lifecycle
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: MemoryQuery,
        context: Optional[MemoryContext] = None,
    ) -> List[MemorySearchHit]:
        text = (query.text or "").strip().lower()
        hits: List[MemorySearchHit] = []

        with self._lock:
            entries = list(self._store.values())

        for entry in entries:
            if not self._matches_filters(entry, query, context):
                continue
            if entry.archived and not query.include_archived:
                continue

            score, matched_on = self._score(entry, text)
            if text and score <= 0:
                continue
            hits.append(MemorySearchHit(entry=deepcopy(entry), score=score, matched_on=matched_on))

        hits.sort(key=lambda h: (-h.score, h.entry.updated_at or ""))
        return hits[: max(1, query.limit)]

    def summarize(self, context: MemoryContext, *, limit: int = 50) -> str:
        self._assert_scope(context)
        query = MemoryQuery(
            text="",
            scopes=[context.scope],
            scope_id=context.scope_id,
            user_id=context.user_id,
            limit=limit,
        )
        hits = self.search(query, context=context)
        if not hits:
            return ""
        lines = [
            f"[{context.scope.value}"
            + (f"/{context.scope_id}" if context.scope_id else "")
            + " memory]"
        ]
        for hit in hits:
            e = hit.entry
            val = e.value
            if isinstance(val, dict) and "value" in val:
                val = val["value"]
            lines.append(f"  - {e.key}: {val}")
        return "\n".join(lines)

    def archive(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        self._assert_scope(context)
        ns = context.namespace_key(key)
        with self._lock:
            entry = self._store.get(ns)
            if entry is None:
                return None
            entry.archived = True
            entry.touch()
            return deepcopy(entry)

    def restore(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        self._assert_scope(context)
        ns = context.namespace_key(key)
        with self._lock:
            entry = self._store.get(ns)
            if entry is None:
                return None
            entry.archived = False
            entry.touch()
            return deepcopy(entry)

    def clear(self, context: MemoryContext) -> int:
        self._assert_scope(context)
        removed = 0
        with self._lock:
            for ns in list(self._store.keys()):
                entry = self._store[ns]
                if self._entry_in_context(entry, context):
                    del self._store[ns]
                    removed += 1
        return removed

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _assert_scope(self, context: MemoryContext) -> None:
        if not self.supports_scope(context.scope):
            raise ValueError(
                f"Provider '{self._name}' does not support scope '{context.scope.value}'"
            )

    @staticmethod
    def _entry_in_context(entry: MemoryEntry, context: MemoryContext) -> bool:
        if entry.context.scope != context.scope:
            return False
        if context.scope_id is not None and entry.context.scope_id != context.scope_id:
            return False
        if context.user_id is not None and entry.context.user_id != context.user_id:
            return False
        return True

    def _matches_filters(
        self,
        entry: MemoryEntry,
        query: MemoryQuery,
        context: Optional[MemoryContext],
    ) -> bool:
        if context is not None and not self._entry_in_context(entry, context):
            return False
        if query.scopes and entry.context.scope not in query.scopes:
            return False
        if query.scope_id is not None and entry.context.scope_id != query.scope_id:
            return False
        if query.user_id is not None and entry.context.user_id != query.user_id:
            return False
        if query.tags:
            if not set(query.tags).issubset(set(entry.tags)):
                return False
        if query.key_prefix and not entry.key.startswith(query.key_prefix):
            return False
        if not self.supports_scope(entry.context.scope):
            return False
        return True

    @staticmethod
    def _score(entry: MemoryEntry, text: str) -> tuple:
        if not text:
            return 1.0, "all"
        key_l = entry.key.lower()
        if key_l == text:
            return 100.0, "key"
        if text in key_l:
            return 50.0, "key"
        val_s = str(entry.value).lower()
        if text in val_s:
            return 25.0, "value"
        for tag in entry.tags:
            if text in tag.lower():
                return 15.0, "tag"
        meta_s = str(entry.metadata).lower()
        if text in meta_s:
            return 10.0, "metadata"
        return 0.0, ""
