"""Conversation / session memory provider.

Wraps the legacy ``memory.conversation_memory`` module without modifying it.
Primary scope: SESSION (conversation history and live session state).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from memory.models import MemoryEntry, MemoryQuery, MemorySearchHit
from memory.provider import IMemoryProvider
from memory.scopes import MemoryContext, MemoryScope


class ConversationMemoryProvider(IMemoryProvider):
    """Adapter over :mod:`memory.conversation_memory`."""

    def __init__(self, name: str = "conversation") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def supported_scopes(self) -> List[MemoryScope]:
        return [MemoryScope.SESSION]

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
        from memory import conversation_memory as cm

        key = (key or "").strip()
        if key == "turn" or key == "append_turn":
            user_text = ""
            lessan_text = ""
            if isinstance(value, dict):
                user_text = str(value.get("user") or value.get("user_text") or "")
                lessan_text = str(
                    value.get("lessan")
                    or value.get("assistant")
                    or value.get("lessan_text")
                    or ""
                )
            cm.append_turn(user_text, lessan_text)
            return self.retrieve(context, "current") or MemoryEntry(
                key="current",
                value={"appended": True},
                context=context,
                provider=self._name,
                metadata=metadata or {},
                tags=list(tags or ["conversation"]),
            )

        if key in ("start", "start_session"):
            cm.start_session()
            return self.retrieve(context, "current") or MemoryEntry(
                key="current",
                value={},
                context=context,
                provider=self._name,
            )

        if key in ("finalize", "finalize_session"):
            finalize = getattr(cm, "finalize_session", None)
            if callable(finalize):
                try:
                    finalize()
                except TypeError:
                    finalize(value) if value else finalize()
            return self.retrieve(context, "current") or MemoryEntry(
                key="current",
                value={"finalized": True},
                context=context,
                provider=self._name,
            )

        return MemoryEntry(
            key=key,
            value=value,
            context=context,
            metadata={**(metadata or {}), "note": "conversation store is append-oriented"},
            tags=list(tags or ["conversation"]),
            provider=self._name,
        )

    def retrieve(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        self._assert_scope(context)
        from memory import conversation_memory as cm

        key = (key or "").strip()
        store = cm.load_conversations()

        if key in ("current", "live"):
            cur = store.get("current")
            if not cur:
                return None
            return MemoryEntry(
                key="current",
                value=dict(cur),
                context=MemoryContext(
                    scope=MemoryScope.SESSION,
                    scope_id=cur.get("id") or context.scope_id,
                    user_id=context.user_id,
                ),
                metadata={"turns": cur.get("turns", 0)},
                tags=["conversation", "live"],
                updated_at=cur.get("last_updated"),
                provider=self._name,
            )

        if key == "recent":
            sessions = []
            if hasattr(cm, "recent_sessions"):
                sessions = cm.recent_sessions()
            else:
                sessions = [s for s in store.get("sessions", []) if s.get("summary")]
            return MemoryEntry(
                key="recent",
                value=sessions,
                context=context,
                tags=["conversation"],
                provider=self._name,
            )

        if key.startswith("session/"):
            sid = key.split("/", 1)[1]
            for s in store.get("sessions", []):
                if s.get("id") == sid:
                    return MemoryEntry(
                        key=key,
                        value=dict(s),
                        context=MemoryContext(
                            scope=MemoryScope.SESSION,
                            scope_id=sid,
                            user_id=context.user_id,
                        ),
                        tags=["conversation"],
                        updated_at=s.get("last_updated"),
                        provider=self._name,
                    )
            return None

        if key == "prompt":
            text = ""
            if hasattr(cm, "format_recent_for_prompt"):
                text = cm.format_recent_for_prompt()
            return MemoryEntry(
                key="prompt",
                value=text,
                context=context,
                tags=["conversation", "prompt"],
                provider=self._name,
            )

        return None

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
        if value is None and patch is not None:
            value = patch
        if value is None:
            return self.retrieve(context, key)
        return self.store(context, key, value, metadata=metadata, tags=tags)

    def delete(self, context: MemoryContext, key: str) -> bool:
        self._assert_scope(context)
        from memory import conversation_memory as cm

        key = (key or "").strip()
        if key.startswith("session/") and hasattr(cm, "forget_sessions"):
            sid = key.split("/", 1)[1]
            removed = cm.forget_sessions(session_id=sid)
            return bool(removed)
        if key in ("all", "history") and hasattr(cm, "forget_sessions"):
            try:
                removed = cm.forget_sessions()
                return bool(removed)
            except TypeError:
                return False
        return False

    def search(
        self,
        query: MemoryQuery,
        context: Optional[MemoryContext] = None,
    ) -> List[MemorySearchHit]:
        from memory import conversation_memory as cm

        if query.scopes and MemoryScope.SESSION not in query.scopes:
            return []

        text = (query.text or "").strip()
        sessions: List[dict] = []

        if text and hasattr(cm, "search_conversations"):
            sessions = cm.search_conversations(text) or []
        elif hasattr(cm, "recent_sessions"):
            sessions = cm.recent_sessions() or []
        else:
            store = cm.load_conversations()
            sessions = list(store.get("sessions") or [])

        if query.scope_id or (context and context.scope_id):
            sid = query.scope_id or (context.scope_id if context else None)
            sessions = [s for s in sessions if s.get("id") == sid]

        hits: List[MemorySearchHit] = []
        for s in sessions:
            sid = s.get("id") or ""
            ctx = MemoryContext(
                scope=MemoryScope.SESSION,
                scope_id=sid,
                user_id=context.user_id if context else query.user_id,
            )
            entry = MemoryEntry(
                key=f"session/{sid}",
                value=dict(s),
                context=ctx,
                tags=["conversation"] + list(s.get("topics") or [])[:5],
                updated_at=s.get("last_updated"),
                provider=self._name,
            )
            if query.key_prefix and not entry.key.startswith(query.key_prefix):
                continue
            score = 1.0
            matched = "all"
            if text:
                blob = " ".join(
                    [
                        str(s.get("summary") or ""),
                        " ".join(str(t) for t in (s.get("topics") or [])),
                        " ".join(str(k) for k in (s.get("key_points") or [])),
                        sid,
                    ]
                ).lower()
                if text.lower() not in blob and text.lower() not in sid.lower():
                    continue
                score = 50.0 if text.lower() in (s.get("summary") or "").lower() else 25.0
                matched = "value"
            hits.append(MemorySearchHit(entry=entry, score=score, matched_on=matched))

        hits.sort(key=lambda h: (-h.score, h.entry.updated_at or ""))
        return hits[: max(1, query.limit)]

    def summarize(self, context: MemoryContext, *, limit: int = 50) -> str:
        self._assert_scope(context)
        from memory import conversation_memory as cm

        if hasattr(cm, "format_recent_for_prompt"):
            block = cm.format_recent_for_prompt()
            if limit and block and len(block) > limit * 40:
                return block[: limit * 40].rstrip() + "…"
            return block or ""
        return ""

    def archive(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        entry = self.retrieve(context, key)
        if entry is None:
            return None
        entry.archived = True
        return entry

    def restore(self, context: MemoryContext, key: str) -> Optional[MemoryEntry]:
        entry = self.retrieve(context, key)
        if entry is None:
            return None
        entry.archived = False
        return entry

    def _assert_scope(self, context: MemoryContext) -> None:
        if not self.supports_scope(context.scope):
            raise ValueError(
                f"Provider '{self._name}' does not support scope '{context.scope.value}'"
            )
