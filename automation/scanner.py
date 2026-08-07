"""Workspace scanning and file search for the File & Command Control System.

The :class:`WorkspaceScanner` walks an approved workspace root, honours the
security policy (never walks into protected/system directories), computes a
:class:`~automation.models.ScanSummary` and answers file-search queries with
:class:`~automation.models.FileMatch` results.

The scanner is read-only. It still goes through the
:class:`~automation.permissions.PermissionManager` for the ``scan_workspace``
and ``search_files`` actions so path-containment rules apply (scanning outside
an approved workspace is denied), but those operations are ``SAFE`` so no
confirmation is ever required.
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.logging import get_logger

from automation.events import EV_SCAN_COMPLETED, emit_automation_event
from automation.models import FileMatch, FileOperationKind, ScanSummary
from automation.permissions import PermissionDeniedError, PermissionManager

logger = get_logger("automation.scanner")

#: Default directory names the scanner never descends into.
DEFAULT_IGNORE = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".venv",
        "__pycache__",
        "node_modules",
        ".trash",
        ".DS_Store",
    }
)

#: File extensions treated as binary (skipped by content scanning).
BINARY_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".gz",
     ".tar", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc"}
)


def _is_binary(path: Path) -> bool:
    """Cheap heuristic: binary extension or a NUL byte in the first chunk."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as handle:
            chunk = handle.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


class WorkspaceScanner:
    """Read-only workspace walker producing :class:`ScanSummary` results.

    Args:
        permission_manager: The :class:`PermissionManager` that gates scanning
            and search operations against the security policy.
        event_bus: Optional event bus for ``automation.scan_completed`` events.
        state_store: Optional state store for the ``automation.last_scan`` slice.
        memory: Optional :class:`MemoryManager` for scan fact storage.
        max_read_chars: Cap for file contents read during content search.
    """

    def __init__(
        self,
        permission_manager: PermissionManager,
        *,
        event_bus: Any = None,
        state_store: Any = None,
        memory: Any = None,
        max_read_chars: int = 100_000,
    ) -> None:
        self._permissions = permission_manager
        self._event_bus = event_bus
        self._state = state_store
        self._memory = memory
        self._max_read_chars = max(1024, int(max_read_chars))
        roots = permission_manager.policy.workspace_roots
        self._default_root = roots[0] if roots else permission_manager.policy.app_root

    @property
    def permissions(self) -> PermissionManager:
        return self._permissions

    @property
    def default_root(self) -> Path:
        return self._default_root

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #
    def scan(
        self,
        root: Any = None,
        *,
        patterns: Optional[List[str]] = None,
        ignore: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        limit: Optional[int] = None,
        skip_protected: bool = True,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> ScanSummary:
        """Walk ``root`` and compute a :class:`ScanSummary`.

        Args:
            root: Directory to scan (defaults to the first workspace root).
            patterns: Optional glob patterns; when given only matching files
                are counted (e.g. ``["*.py", "*.md"]``).
            ignore: Extra basename globs to skip (merged with the defaults).
            max_depth: Maximum directory depth below ``root`` (``None`` = all).
            limit: Stop after this many files (sets ``truncated``).
            skip_protected: Never descend into policy-protected directories.
            actor: Operation actor for the permission check / audit.
            workspace: Workspace name to record in events and memory.
        """
        root_path = self._resolve(root)
        decision = self._permissions.check(
            FileOperationKind.SCAN_WORKSPACE,
            source=root_path,
            actor=actor,
            workspace=workspace,
        )
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason, decision=decision)
        if not root_path.exists():
            raise FileNotFoundError(root_path)
        if not root_path.is_dir():
            raise NotADirectoryError(root_path)

        started = time.time()
        ignore_set = set(DEFAULT_IGNORE)
        ignore_set.update(ignore or ())
        compiled = [re.compile(fnmatch.translate(p)) for p in (patterns or ())]

        file_count = 0
        dir_count = 0
        total_bytes = 0
        largest: List[Dict[str, Any]] = []
        newest: List[Dict[str, Any]] = []
        extensions: Counter = Counter()
        truncated = False

        for entry, kind in self._iter_entries(
            root_path,
            ignore=ignore_set,
            max_depth=max_depth,
            skip_protected=skip_protected,
        ):
            if kind == "dir":
                dir_count += 1
                continue
            if compiled and not any(p.search(entry.name) for p in compiled):
                continue
            try:
                info = entry.stat()
            except OSError:
                continue
            file_count += 1
            total_bytes += info.st_size
            extensions[entry.suffix.lower()] += 1

            item = {
                "path": str(entry),
                "name": entry.name,
                "size": info.st_size,
                "modified": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
            }
            largest.append(item)
            largest.sort(key=lambda d: d["size"], reverse=True)
            del largest[5:]
            newest.append(item)
            newest.sort(key=lambda d: d["modified"], reverse=True)
            del newest[5:]

            if limit is not None and file_count >= limit:
                truncated = True
                break

        summary = ScanSummary(
            root=str(root_path),
            file_count=file_count,
            dir_count=dir_count,
            total_bytes=total_bytes,
            largest=largest,
            newest=newest,
            extensions=dict(extensions),
            duration_ms=(time.time() - started) * 1000.0,
            truncated=truncated,
        )
        self._record(summary, workspace)
        return summary

    def find_files(
        self,
        *,
        root: Any = None,
        query: Optional[str] = None,
        name: Optional[str] = None,
        extension: Optional[str] = None,
        pattern: Optional[str] = None,
        content: Optional[str] = None,
        max_results: int = 100,
        snippet: bool = True,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search a workspace root and return :class:`FileMatch` entries.

        ``query`` is a case-insensitive substring of the file name; ``name`` is
        a fnmatch glob on the file name; ``extension`` filters by suffix;
        ``pattern`` is a regex on the full path; ``content`` is a case-sensitive
        substring of the file body (binary files are skipped).
        """
        root_path = self._resolve(root)
        decision = self._permissions.check(
            FileOperationKind.SEARCH_FILES,
            source=root_path,
            actor=actor,
            workspace=workspace,
        )
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason, decision=decision)
        if not root_path.exists():
            raise FileNotFoundError(root_path)

        needle = (query or "").lower()
        name_pattern = re.compile(fnmatch.translate(name)) if name else None
        path_pattern = re.compile(pattern) if pattern else None
        ext = extension.lstrip(".").lower() if extension else None

        matches: List[FileMatch] = []
        for entry in root_path.rglob("*"):
            if not entry.is_file():
                continue
            if needle and needle not in entry.name.lower():
                continue
            if name_pattern and not name_pattern.search(entry.name):
                continue
            if ext and not entry.name.lower().endswith(f".{ext}"):
                continue
            if path_pattern and not path_pattern.search(str(entry)):
                continue
            snippet_text = None
            if content:
                if _is_binary(entry):
                    continue
                try:
                    text = entry.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                index = text.find(content)
                if index == -1:
                    continue
                if snippet:
                    snippet_text = self._snippet(text, index, 120)
            try:
                info = entry.stat()
                modified = datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds")
            except OSError:
                info = None
                modified = None
            matches.append(
                FileMatch(
                    path=str(entry),
                    name=entry.name,
                    size=info.st_size if info else None,
                    modified=modified,
                    snippet=snippet_text,
                )
            )
            if len(matches) >= max_results:
                break

        return {
            "root": str(root_path),
            "matches": [m.as_dict() for m in matches],
            "count": len(matches),
        }

    # ----------------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------------- #
    def _resolve(self, path: Any) -> Path:
        candidate = Path(path) if path is not None else self._default_root
        if not candidate.is_absolute():
            candidate = self._default_root / candidate
        return candidate.expanduser().resolve()

    def _iter_entries(
        self,
        root: Path,
        *,
        ignore: set,
        max_depth: Optional[int],
        skip_protected: bool,
    ) -> Iterable[Tuple[Path, str]]:
        """Yield ``(path, kind)`` for every non-ignored entry under ``root``."""
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            try:
                rel = current_path.relative_to(root)
            except ValueError:
                continue
            depth = 0 if str(rel) == "." else len(rel.parts)
            keep = max_depth is None or depth + 1 <= max_depth

            dirs[:] = [
                d
                for d in sorted(dirs)
                if not self._is_ignored(d, ignore)
                and not (skip_protected and self._is_protected(current_path / d))
            ]
            if not keep:
                dirs[:] = []
                files = []
            else:
                files = [f for f in sorted(files) if not self._is_ignored(f, ignore)]
            for name in dirs:
                yield current_path / name, "dir"
            for name in files:
                yield current_path / name, "file"

    def _is_protected(self, path: Path) -> bool:
        try:
            return self._permissions.policy.is_protected(path)
        except Exception:  # noqa: BLE001 - policy lookups must not crash scans
            return False

    @staticmethod
    def _is_ignored(name: str, ignore: set) -> bool:
        for pattern in ignore:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def _record(self, summary: ScanSummary, workspace: Optional[str]) -> None:
        emit_automation_event(EV_SCAN_COMPLETED, summary.as_dict(), bus=self._event_bus)
        if self._state is not None:
            try:
                self._state.update("automation.last_scan", summary.as_dict())
            except Exception:  # noqa: BLE001
                pass
        self._store_memory(summary.as_dict(), workspace)

    def _store_memory(self, payload: Dict[str, Any], workspace: Optional[str]) -> None:
        if self._memory is None:
            return
        try:
            from memory import MemoryContext, MemoryScope

            context = MemoryContext(
                scope=MemoryScope.WORKSPACE, scope_id=workspace or "default"
            )
            self._memory.store(
                context,
                f"scan:{time.time_ns():x}",
                payload,
                tags=["automation", "scan"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Could not record scan fact: {exc}")

    @staticmethod
    def _snippet(text: str, start: int, width: int) -> str:
        """Build a ``width``-char snippet around ``start``."""
        half = width // 2
        begin = max(0, start - half)
        end = min(len(text), start + half)
        prefix = "..." if begin > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[begin:end]}{suffix}"



