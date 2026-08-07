"""Long-term knowledge / user preferences provider.

Wraps the legacy ``memory.memory_manager`` function API without modifying it.
Maps categories (identity, preferences, projects, …) onto USER and GLOBAL
scopes for the Unified Memory System.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from memory.models import MemoryEntry, MemoryQuery, MemorySearchHit
from memory.provider import IMemoryProvider
from memory.scopes import MemoryContext, MemoryScope

_VALID_CATEGORIES = frozenset(
    {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
)
_GLOBAL_CATEGORIES = frozenset({"notes"})


class LongTermMemoryProvider(IMemoryProvider):
    """Adapter over :mod:`memory.memory_manager` (JSON long_term store)."""

    def __init__(self, name: str = "long_term") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def supported_scopes(self) -> List[MemoryScope]:
        return [MemoryScope.USER, MemoryScope.GLOBAL]

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
        category, item = self._split_key(key)
        from memory.memory_manager import remember, load_memory

        plain = self._to_plain(value)
        remember(item, plain, category=category)
        memory = load_memory()
        entry = self._entry_from_store(context, category, item, memory)
        if metadata:
            entry.metadata.update(metadata)
        if tags:
            entry.tags = list(tags)
        entry.provider = self._name
        return entry

    def retrieve(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        self._assert_scope(context)
        category, item = self._split_key(key)
        from memory.memory_manager import load_memory

        memory = load_memory()
        cat = memory.get(category) or {}
        if item not in cat:
            return None
        return self._entry_from_store(context, category, item, memory)

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
        existing = self.retrieve(context, key)
        if existing is None:
            return None
        new_value = value
        if new_value is None and patch is not None:
            if isinstance(existing.value, dict):
                new_value = {**existing.value, **patch}
            else:
                new_value = patch
        if new_value is None:
            new_value = existing.value
        return self.store(
            context,
            key,
            new_value,
            metadata=metadata if metadata is not None else existing.metadata,
            tags=tags if tags is not None else existing.tags,
        )

    def delete(self, context: MemoryContext, key: str) -> bool:
        self._assert_scope(context)
        category, item = self._split_key(key)
        from memory.memory_manager import forget

        result = forget(item, category=category)
        return result.startswith("Forgotten")

    def search(
        self,
        query: MemoryQuery,
        context: Optional[MemoryContext] = None,
    ) -> List[MemorySearchHit]:
        from memory.memory_manager import load_memory

        memory = load_memory()
        text = (query.text or "").strip().lower()
        hits: List[MemorySearchHit] = []

        scopes = query.scopes
        if context is not None:
            scopes = [context.scope]
        if scopes is None:
            scopes = self.supported_scopes()
        allowed = [s for s in scopes if self.supports_scope(s)]
        if not allowed:
            return []

        use_scope = context.scope if context else allowed[0]

        for category, items in memory.items():
            if not isinstance(items, dict):
                continue
            for item_key, raw in items.items():
                full_key = f"{category}/{item_key}"
                if query.key_prefix and not (
                    full_key.startswith(query.key_prefix)
                    or item_key.startswith(query.key_prefix)
                ):
                    continue
                ctx = MemoryContext(
                    scope=use_scope,
                    scope_id=context.scope_id if context else query.scope_id,
                    user_id=context.user_id if context else query.user_id,
                )
                entry = self._build_entry(ctx, category, item_key, raw)
                if query.tags and not set(query.tags).issubset(set(entry.tags)):
                    continue
                if entry.archived and not query.include_archived:
                    continue
                score, matched = self._score(entry, text, category)
                if text and score <= 0:
                    continue
                hits.append(MemorySearchHit(entry=entry, score=score, matched_on=matched))

        hits.sort(key=lambda h: (-h.score, h.entry.updated_at or ""))
        return hits[: max(1, query.limit)]

    def summarize(self, context: MemoryContext, *, limit: int = 50) -> str:
        self._assert_scope(context)
        from memory.memory_manager import format_memory_for_prompt, load_memory

        block = format_memory_for_prompt(load_memory())
        if limit and block and len(block) > limit * 40:
            return block[: limit * 40].rstrip() + "…"
        return block or ""

    def archive(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        existing = self.retrieve(context, key)
        if existing is None:
            return None
        category, item = self._split_key(key)
        from memory.memory_manager import remember, forget

        remember(
            f"archived_{category}_{item}",
            str(self._to_plain(existing.value)),
            category="notes",
        )
        forget(item, category=category)
        existing.archived = True
        existing.key = f"{category}/__archived__/{item}"
        existing.touch()
        return existing

    def restore(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        category, item = self._split_key(key.replace("__archived__/", ""))
        from memory.memory_manager import load_memory, remember, forget

        notes = (load_memory().get("notes") or {})
        note_key = f"archived_{category}_{item}"
        raw = notes.get(note_key)
        if raw is None:
            parts = key.split("/")
            if len(parts) >= 3 and parts[1] == "__archived__":
                category, item = parts[0], parts[2]
                note_key = f"archived_{category}_{item}"
                raw = notes.get(note_key)
        if raw is None:
            return None
        value = raw.get("value") if isinstance(raw, dict) else raw
        remember(item, str(value), category=category)
        forget(note_key, category="notes")
        return self.retrieve(context, f"{category}/{item}")

    def _assert_scope(self, context: MemoryContext) -> None:
        if not self.supports_scope(context.scope):
            raise ValueError(
                f"Provider '{self._name}' does not support scope '{context.scope.value}'"
            )

    @staticmethod
    def _split_key(key: str) -> tuple:
        key = (key or "").strip().strip("/")
        if "/" in key:
            category, item = key.split("/", 1)
            category = category if category in _VALID_CATEGORIES else "notes"
            item = item.replace("__archived__/", "")
            return category, item
        return "notes", key

    @staticmethod
    def _to_plain(value: Any) -> str:
        if isinstance(value, dict) and "value" in value:
            return str(value["value"])
        return str(value)

    def _entry_from_store(
        self,
        context: MemoryContext,
        category: str,
        item: str,
        memory: dict,
    ) -> MemoryEntry:
        raw = (memory.get(category) or {}).get(item)
        return self._build_entry(context, category, item, raw)

    def _build_entry(
        self,
        context: MemoryContext,
        category: str,
        item: str,
        raw: Any,
    ) -> MemoryEntry:
        if isinstance(raw, dict) and "value" in raw:
            value = raw.get("value")
            updated = raw.get("updated")
        else:
            value = raw
            updated = None
        return MemoryEntry(
            key=f"{category}/{item}",
            value=value,
            context=context,
            metadata={"category": category},
            tags=[category],
            updated_at=updated,
            created_at=updated,
            provider=self._name,
        )

    @staticmethod
    def _score(entry: MemoryEntry, text: str, category: str) -> tuple:
        if not text:
            return 1.0, "all"
        key_l = entry.key.lower()
        if key_l == text or entry.key.split("/")[-1].lower() == text:
            return 100.0, "key"
        if text in key_l:
            return 50.0, "key"
        if text in category.lower():
            return 40.0, "tag"
        val_s = str(entry.value).lower()
        if text in val_s:
            return 25.0, "value"
        return 0.0, ""
