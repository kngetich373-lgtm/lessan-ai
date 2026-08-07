"""Filesystem watching for the File & Command Control System.

The :class:`FileWatcher` is a lightweight, dependency-free *polling* watcher:
every ``interval`` seconds it re-scans the watched workspace roots and diffs
the previous snapshot, producing :class:`~automation.models.WatcherEvent`
records (created / modified / deleted).

Each change is pushed to a bounded event buffer and published on the event bus
as ``automation.watch_event``. The watcher never watches policy-protected
directories (``.git``, ``.venv``, ``node_modules``, ``__pycache__``, ...).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from core.logging import get_logger

from automation.events import EV_WATCH_EVENT, emit_automation_event
from automation.models import WatcherEvent
from automation.permissions import PermissionDeniedError, PermissionManager

logger = get_logger("automation.watcher")

#: Directories that are never watched.
WATCH_IGNORE = frozenset(
    {".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__", ".trash"}
)

#: A snapshot entry: (mtime_ns, size, is_dir).
_Snapshot = Dict[str, Tuple[int, int, bool]]


class FileWatcher:
    """Threaded polling watcher for workspace directories.

    Args:
        permission_manager: The :class:`PermissionManager` used to approve the
            watched root at :meth:`start` time.
        event_bus: Optional event bus for ``automation.watch_event`` events.
        state_store: Optional state store for the ``automation.watcher`` slices.
        memory: Optional :class:`MemoryManager` for watch-event storage.
        interval: Default polling interval in seconds.
        max_events: Bounded size of the in-memory event buffer.
    """

    def __init__(
        self,
        permission_manager: PermissionManager,
        *,
        event_bus: Any = None,
        state_store: Any = None,
        memory: Any = None,
        interval: float = 2.0,
        max_events: int = 500,
    ) -> None:
        self._permissions = permission_manager
        self._event_bus = event_bus
        self._state = state_store
        self._memory = memory
        self._interval = max(0.1, float(interval))
        self._max_events = max(10, int(max_events))
        self._events: Deque[WatcherEvent] = deque(maxlen=self._max_events)
        self._snapshots: Dict[Path, _Snapshot] = {}
        self._patterns: Set[str] = set()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def permissions(self) -> PermissionManager:
        return self._permissions

    @property
    def interval(self) -> float:
        return self._interval

    # ----------------------------------------------------------------------- #
    # Lifecycle
    # ----------------------------------------------------------------------- #
    def start(
        self,
        root: Any = None,
        *,
        interval: Optional[float] = None,
        patterns: Optional[List[str]] = None,
        actor: str = "user",
    ) -> "FileWatcher":
        """Begin watching ``root`` in a background thread.

        Args:
            root: Directory to watch (defaults to the first workspace root).
            interval: Poll interval override (seconds).
            patterns: Optional glob patterns that restrict which files are
                observed (e.g. ``["*.py", "*.md"]``).
            actor: Actor for the initial permission check / audit.

        Returns:
            ``self`` so calls can be chained.
        """
        root_path = self._resolve(root)
        decision = self._permissions.check(
            "scan_workspace",
            source=root_path,
            actor=actor,
        )
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason, decision=decision)

        if interval is not None:
            self._interval = max(0.1, float(interval))
        with self._lock:
            self._patterns = set(patterns or ())
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._poll_loop,
                    name="automation-watcher",
                    daemon=True,
                )
                self._thread.start()
                # Build the baseline synchronously so the first cycle is quiet.
                self._snapshots[root_path] = self._build_snapshot(root_path)
        logger.info(f"FileWatcher started on {root_path} (interval={self._interval}s)")
        return self

    def stop(self, join: bool = True) -> None:
        """Stop the watcher thread."""
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and join:
            thread.join(timeout=max(self._interval * 2, 2.0))
        logger.info("FileWatcher stopped")

    def clear(self) -> None:
        """Drop buffered events (snapshots are kept)."""
        with self._lock:
            self._events.clear()

    # ----------------------------------------------------------------------- #
    # Polling
    # ----------------------------------------------------------------------- #
    def snapshot(self) -> List[Dict[str, Any]]:
        """Run a single poll cycle and return the observed changes.

        The first call for a root builds the baseline and returns ``[]``.
        Safe to call even when the background thread is not running.
        """
        with self._lock:
            roots = list(self._snapshots) if self._snapshots else []
        if not roots:
            roots = [self._resolve(None)]
        changes: List[Dict[str, Any]] = []
        for root in roots:
            changes.extend(self._poll_once(root))
        return changes

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the newest buffered events as dictionaries."""
        with self._lock:
            events = list(self._events)
        return [e.as_dict() for e in events[: max(0, limit)]]

    # ----------------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------------- #
    def _resolve(self, path: Any) -> Path:
        first_root = self._permissions.policy.workspace_roots[0]
        candidate = Path(path) if path is not None else first_root
        if not candidate.is_absolute():
            candidate = first_root / candidate
        return candidate.expanduser().resolve()

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    roots = list(self._snapshots)
                for root in roots:
                    self._poll_once(root)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                logger.debug(f"Watcher poll error: {exc}")
            self._stop_event.wait(timeout=self._interval)

    def _poll_once(self, root: Path) -> List[Dict[str, Any]]:
        before = self._snapshots.get(root)
        after = self._build_snapshot(root)
        with self._lock:
            self._snapshots[root] = after
        if before is None:
            return []  # baseline
        events = self._diff(root, before, after)
        for event in events:
            self._record(event)
        return [e.as_dict() for e in events]

    def _build_snapshot(self, root: Path) -> _Snapshot:
        snapshot: _Snapshot = {}
        if not root.exists():
            return snapshot
        for entry in root.rglob("*"):
            if entry.name in WATCH_IGNORE:
                continue
            if entry.is_dir():
                continue
            try:
                info = entry.stat()
            except OSError:
                continue
            rel = str(entry.relative_to(root))
            if self._patterns and not self._glob_match(rel, self._patterns):
                continue
            snapshot[rel] = (info.st_mtime_ns, info.st_size, False)
        return snapshot

    def _diff(self, root: Path, before: _Snapshot, after: _Snapshot) -> List[WatcherEvent]:
        events: List[WatcherEvent] = []
        for rel, state in after.items():
            if rel not in before:
                events.append(WatcherEvent("created", str(root / rel)))
            elif state[:2] != before[rel][:2]:
                events.append(
                    WatcherEvent(
                        "modified",
                        str(root / rel),
                        size=state[1],
                        modified=time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time())
                        ),
                    )
                )
        for rel in before:
            if rel not in after:
                events.append(WatcherEvent("deleted", str(root / rel)))
        return events

    def _record(self, event: WatcherEvent) -> None:
        with self._lock:
            self._events.append(event)
        emit_automation_event(EV_WATCH_EVENT, event.as_dict(), bus=self._event_bus)
        if self._state is not None:
            try:
                self._state.update("automation.watcher.last_event", event.as_dict())
            except Exception:  # noqa: BLE001
                pass
        self._store_memory(event)

    def _store_memory(self, event: WatcherEvent) -> None:
        if self._memory is None:
            return
        try:
            from memory import MemoryContext, MemoryScope

            context = MemoryContext(scope=MemoryScope.WORKSPACE, scope_id="default")
            self._memory.store(
                context,
                f"watch:{time.time_ns():x}",
                event.as_dict(),
                tags=["automation", "watcher", event.event_type],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Could not record watch event: {exc}")

    @staticmethod
    def _glob_match(rel: str, patterns: set) -> bool:
        import fnmatch

        return any(
            fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(Path(rel).name, p)
            for p in patterns
        )




