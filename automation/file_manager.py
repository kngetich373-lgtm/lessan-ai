"""Workspace file operations for the File & Command Control System.

:class:`WorkspaceFileManager` is the *safe* filesystem surface for Lessan AI:
every operation is checked by the :class:`PermissionManager` (path
containment, system-path and protected-path rules, danger escalation) before
touching disk.

Design notes:

* **Relative paths** are resolved against the manager's ``default_root``
  (the first approved workspace).
* **Deletes are soft** by default — files move to a ``.trash`` folder inside
  the workspace instead of being permanently removed (pass
  ``permanent=True`` for a hard delete).
* Every mutation emits a dedicated event (``automation.file_created``, ...)
  and is mirrored to the state store and memory, so the event bus and memory
  manager can subscribe without depending on this module.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import time
from datetime import datetime
from fnmatch import translate as fnmatch_translate
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger

from automation.events import (
    EV_BATCH_COMPLETED,
    EV_FILE_COPIED,
    EV_FILE_CREATED,
    EV_FILE_DELETED,
    EV_FILE_MODIFIED,
    EV_FILE_MOVED,
    EV_FILE_OPENED,
    EV_FILE_RENAMED,
    EV_FOLDER_CREATED,
    EV_FOLDER_DELETED,
    emit_automation_event,
)
from automation.models import FileMatch, FileOperationKind
from automation.permissions import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    PermissionManager,
)

logger = get_logger("automation.files")

# Maximum number of bytes read for content search / binary detection.
_BINARY_PROBE_BYTES = 8192


def _is_binary(path: Path) -> bool:
    """Heuristic binary detection: NUL bytes in the first probe chunk."""
    try:
        with path.open("rb") as handle:
            chunk = handle.read(_BINARY_PROBE_BYTES)
        return b"\x00" in chunk
    except OSError:
        return True


def _default_open_file(path: str) -> bool:
    """Fallback "open in editor" implementation (works on common desktops)."""
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        import subprocess

        opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
        subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not open {path}: {exc}")
        return False

class WorkspaceFileManager:
    """Safe file and folder operations inside the approved workspace."""

    def __init__(
        self,
        permission_manager: PermissionManager,
        *,
        event_bus: Any = None,
        state_store: Any = None,
        memory: Any = None,
        default_root: Any = None,
        trash_enabled: bool = True,
        open_file_func: Any = None,
    ) -> None:
        self._permissions = permission_manager
        self._event_bus = event_bus
        self._state = state_store
        self._memory = memory
        if default_root is None:
            default_root = permission_manager.policy.workspace_roots[0]
        self._default_root = Path(default_root).expanduser().resolve()
        self._trash_enabled = trash_enabled
        self._open_file = open_file_func or _default_open_file

    @property
    def permissions(self) -> PermissionManager:
        return self._permissions

    @property
    def default_root(self) -> Path:
        return self._default_root

    # ----------------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------------- #
    def _resolve(self, path: Any) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._default_root / candidate
        return candidate.expanduser().resolve()

    def _gate(
        self,
        kind: FileOperationKind,
        *,
        source: Any = None,
        destination: Any = None,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
        recursive: bool = False,
    ) -> Any:
        """Run the permission check and return the decision (or raise)."""
        decision = self._permissions.check(
            kind,
            source=source,
            destination=destination,
            actor=actor,
            workspace=workspace,
            recursive=recursive,
        )
        if decision.allowed:
            return decision
        if decision.requires_confirmation:
            if confirm and decision.token and self._permissions.confirm(decision.token, actor=actor):
                return decision
            raise ConfirmationRequiredError(decision.reason, token=decision.token, decision=decision)
        raise PermissionDeniedError(decision.reason, decision=decision)

    def _record(self, kind: FileOperationKind, payload: Dict[str, Any], workspace: Optional[str] = None) -> None:
        emit_automation_event(kind, payload, bus=self._event_bus)
        if self._state is not None:
            try:
                self._state.update("automation.last_file_op", payload)
            except Exception:  # noqa: BLE001
                pass
        self._store_memory(f"file_op:{time.time_ns():x}", payload, workspace)

    def _store_memory(self, key: str, payload: Dict[str, Any], workspace: Optional[str]) -> None:
        if self._memory is None:
            return
        try:
            from memory import MemoryContext, MemoryScope

            context = MemoryContext(scope=MemoryScope.WORKSPACE, scope_id=workspace or "default")
            self._memory.store(context, key, payload, tags=["automation", "file_operations"])
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Could not record memory fact: {exc}")

    def _workspace_root(self, path: Path) -> Optional[Path]:
        profile = self._permissions.policy.workspace_for(path)
        return profile.root if profile else None

    def _trash(self, path: Path) -> Path:
        """Move a path into the workspace-local ``.trash`` folder."""
        root = self._workspace_root(path) or self._default_root
        trash_dir = root / ".trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        destination = trash_dir / f"{stamp}_{path.name}"
        counter = 1
        while destination.exists():
            destination = trash_dir / f"{stamp}_{counter}_{path.name}"
            counter += 1
        shutil.move(str(path), str(destination))
        return destination


    # ----------------------------------------------------------------------- #
    # Folder operations
    # ----------------------------------------------------------------------- #
    def create_folder(
        self,
        path: Any,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Create a folder (and any missing parents)."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.CREATE_FOLDER,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        target.mkdir(parents=True, exist_ok=True)
        payload = {"path": str(target), "kind": "folder", "actor": actor}
        self._record(EV_FOLDER_CREATED, payload, workspace)
        return payload

    def rename(
        self,
        source: Any,
        destination: Any,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Rename a file or folder within the workspace."""
        src = self._resolve(source)
        dest = self._resolve(destination)
        kind = FileOperationKind.RENAME_FOLDER if src.is_dir() else FileOperationKind.RENAME_FILE
        self._gate(
            kind,
            source=src,
            destination=dest,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        if not src.exists():
            raise FileNotFoundError(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        payload = {"path": str(dest), "source": str(src), "destination": str(dest), "actor": actor}
        self._record(EV_FILE_RENAMED, payload, workspace)
        return payload

    def move(
        self,
        source: Any,
        destination: Any,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Move a file or folder to a new location in the workspace."""
        src = self._resolve(source)
        dest = self._resolve(destination)
        kind = FileOperationKind.MOVE_FOLDER if src.is_dir() else FileOperationKind.MOVE_FILE
        self._gate(
            kind,
            source=src,
            destination=dest,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        if not src.exists():
            raise FileNotFoundError(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        payload = {"path": str(dest), "source": str(src), "destination": str(dest), "actor": actor}
        self._record(EV_FILE_MOVED, payload, workspace)
        return payload

    def copy(
        self,
        source: Any,
        destination: Any,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Copy a file or folder to a new location in the workspace."""
        src = self._resolve(source)
        dest = self._resolve(destination)
        kind = FileOperationKind.COPY_FOLDER if src.is_dir() else FileOperationKind.COPY_FILE
        self._gate(
            kind,
            source=src,
            destination=dest,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        if not src.exists():
            raise FileNotFoundError(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dest), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dest))
        payload = {"path": str(dest), "source": str(src), "destination": str(dest), "actor": actor}
        self._record(EV_FILE_COPIED, payload, workspace)
        return payload


    def delete_folder(
        self,
        path: Any,
        *,
        recursive: bool = True,
        permanent: bool = False,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Delete a folder (soft delete moves it to ``.trash``)."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.DELETE_FOLDER,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
            recursive=recursive,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        if not target.is_dir():
            raise NotADirectoryError(target)
        if not recursive and any(target.iterdir()):
            raise OSError(f"folder is not empty: {target}")

        if self._trash_enabled and not permanent:
            destination = self._trash(target)
        else:
            shutil.rmtree(str(target))
            destination = str(target)
        payload = {"path": str(target), "trashed": str(destination), "actor": actor, "permanent": permanent}
        self._record(EV_FOLDER_DELETED, payload, workspace)
        return payload

    def list_directory(
        self,
        path: Any = None,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List a directory's entries (sorted, with basic metadata)."""
        target = self._resolve(path) if path is not None else self._default_root
        self._gate(
            FileOperationKind.LIST_DIRECTORY,
            source=target,
            actor=actor,
            workspace=workspace,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        if not target.is_dir():
            raise NotADirectoryError(target)
        entries = []
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                info = entry.stat()
                modified = datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds")
            except OSError:
                info = None
                modified = None
            entries.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "kind": "folder" if entry.is_dir() else "file",
                    "size": info.st_size if info else None,
                    "modified": modified,
                }
            )
        return {"path": str(target), "entries": entries, "count": len(entries)}


    # ----------------------------------------------------------------------- #
    # File operations
    # ----------------------------------------------------------------------- #
    def create_file(
        self,
        path: Any,
        content: str = "",
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Create a file with ``content`` (parents are created too)."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.CREATE_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(target)
        target.write_text(content or "", encoding="utf-8")
        payload = {"path": str(target), "bytes": len(content or ""), "actor": actor}
        self._record(EV_FILE_CREATED, payload, workspace)
        return payload

    def read_file(
        self,
        path: Any,
        *,
        max_chars: Optional[int] = None,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read a text file (binary files are detected and reported)."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.READ_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        if target.is_dir():
            raise IsADirectoryError(target)
        stat_result = target.stat()
        modified = datetime.fromtimestamp(stat_result.st_mtime).isoformat(timespec="seconds")
        binary = _is_binary(target)
        if binary:
            content = ""
            size = stat_result.st_size
        else:
            raw = target.read_text(encoding="utf-8", errors="replace")
            size = len(raw)
            content = raw[:max_chars] if (max_chars is not None and len(raw) > max_chars) else raw
        payload = {
            "path": str(target),
            "content": content,
            "bytes": size,
            "size": stat_result.st_size,
            "modified": modified,
            "binary": binary,
            "truncated": bool(max_chars is not None and size > max_chars),
        }
        self._record(EV_FILE_OPENED, {"path": str(target), "actor": actor}, workspace)
        return payload

    def write_file(
        self,
        path: Any,
        content: str,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Overwrite a file with ``content``."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.WRITE_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
        payload = {"path": str(target), "bytes": len(content or ""), "actor": actor}
        self._record(EV_FILE_MODIFIED, payload, workspace)
        return payload


    def edit_file(
        self,
        path: Any,
        old_text: Optional[str] = None,
        new_text: Optional[str] = None,
        *,
        count: int = 1,
        regex: bool = False,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Replace ``old_text`` with ``new_text`` in a file.

        When ``old_text`` is ``None`` the file is overwritten with
        ``new_text``. Use ``count=-1`` for all occurrences and
        ``regex=True`` to interpret the pattern as a regular expression.
        """
        target = self._resolve(path)
        self._gate(
            FileOperationKind.EDIT_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        if target.is_dir():
            raise IsADirectoryError(target)
        original = target.read_text(encoding="utf-8", errors="replace")
        if old_text is None:
            replacement = new_text or ""
            replaced = 1 if replacement != original else 0
        elif regex:
            pattern = re.compile(old_text)
            max_count = -1 if count == -1 else max(1, count)
            replacement, replaced = pattern.subn(new_text or "", original, max_count)
        else:
            max_count = -1 if count == -1 else max(1, count)
            replacement = original.replace(old_text, new_text or "", max_count)
            replaced = original.count(old_text)
            if count not in (-1, 1):
                replaced = min(replaced, max_count)
        if replacement != original:
            target.write_text(replacement, encoding="utf-8")
        payload = {"path": str(target), "replaced": replaced, "bytes": len(replacement), "actor": actor}
        self._record(EV_FILE_MODIFIED, payload, workspace)
        return payload

    def append_file(
        self,
        path: Any,
        content: str,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Append ``content`` to a file (created if missing)."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.APPEND_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content or "")
        size = target.stat().st_size
        payload = {"path": str(target), "bytes": len(content or ""), "size": size, "actor": actor}
        self._record(EV_FILE_MODIFIED, payload, workspace)
        return payload

    def delete_file(
        self,
        path: Any,
        *,
        permanent: bool = False,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Delete a file (soft delete moves it to ``.trash``)."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.DELETE_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        if target.is_dir():
            raise IsADirectoryError(target)
        if self._trash_enabled and not permanent:
            destination = self._trash(target)
        else:
            target.unlink()
            destination = str(target)
        payload = {"path": str(target), "trashed": str(destination), "actor": actor, "permanent": permanent}
        self._record(EV_FILE_DELETED, payload, workspace)
        return payload


    # ----------------------------------------------------------------------- #
    # Search, replace and batch
    # ----------------------------------------------------------------------- #
    def search_files(
        self,
        *,
        root: Any = None,
        name: Optional[str] = None,
        extension: Optional[str] = None,
        pattern: Optional[str] = None,
        content: Optional[str] = None,
        regex: bool = False,
        max_results: int = 100,
        recursive: bool = True,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search the workspace for files by name, extension or content."""
        root_path = self._resolve(root) if root is not None else self._default_root
        self._gate(
            FileOperationKind.SEARCH_FILES,
            source=root_path,
            actor=actor,
            workspace=workspace,
        )
        if not root_path.exists():
            raise FileNotFoundError(root_path)

        name_pattern = re.compile(fnmatch_translate(name)) if name else None
        ext = extension.lstrip(".").lower() if extension else None
        path_pattern = re.compile(pattern) if pattern else None
        content_pattern = re.compile(content) if (content and regex) else None

        matches: List[FileMatch] = []
        iterator = root_path.rglob("*") if recursive else root_path.glob("*")
        for entry in iterator:
            if not entry.is_file():
                continue
            rel = entry.name
            if name_pattern and not name_pattern.search(rel):
                continue
            if ext and not rel.lower().endswith(f".{ext}"):
                continue
            if path_pattern and not path_pattern.search(str(entry)):
                continue
            snippet = None
            if content:
                if _is_binary(entry):
                    continue
                try:
                    text = entry.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if regex:
                    match = content_pattern.search(text)
                    if not match:
                        continue
                    snippet = self._snippet(text, match.start(), 120)
                else:
                    index = text.find(content)
                    if index == -1:
                        continue
                    snippet = self._snippet(text, index, 120)
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
                    snippet=snippet,
                )
            )
            if len(matches) >= max_results:
                break

        return {"root": str(root_path), "matches": [m.as_dict() for m in matches], "count": len(matches)}


    def replace_text(
        self,
        source: Any,
        old_text: str,
        new_text: str,
        *,
        regex: bool = False,
        count: int = -1,
        recursive: bool = False,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Replace text across one file or every file under a folder."""
        target = self._resolve(source)
        self._gate(
            FileOperationKind.REPLACE_TEXT,
            source=target,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        files = [target]
        if target.is_dir():
            if not recursive:
                raise OSError(f"replace_text on a folder requires recursive=True: {target}")
            files = [p for p in target.rglob("*") if p.is_file() and not _is_binary(p)]

        total_replacements = 0
        per_file: Dict[str, int] = {}
        max_count = -1 if count == -1 else max(1, count)
        for entry in files:
            if _is_binary(entry):
                continue
            try:
                original = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if regex:
                pattern = re.compile(old_text)
                replacement, replaced = pattern.subn(new_text or "", original, max_count)
            else:
                replacement = original.replace(old_text, new_text or "", max_count)
                replaced = original.count(old_text)
                if count not in (-1, 1):
                    replaced = min(replaced, max_count)
            if replaced and replacement != original:
                entry.write_text(replacement, encoding="utf-8")
                per_file[str(entry)] = replaced
                total_replacements += replaced
                self._record(EV_FILE_MODIFIED, {"path": str(entry), "replaced": replaced, "actor": actor}, workspace)

        payload = {
            "files": len(per_file),
            "total_replacements": total_replacements,
            "per_file": per_file,
            "actor": actor,
        }
        self._record(EV_BATCH_COMPLETED, payload, workspace)
        return payload

    def batch(
        self,
        operations: List[Dict[str, Any]],
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Run a list of operations (dicts with an ``action`` key) in order."""
        if not isinstance(operations, list) or not operations:
            raise ValueError("batch requires a non-empty list of operations")
        root = workspace or str(self._default_root)
        self._gate(
            FileOperationKind.BATCH,
            source=root,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )
        results = []
        failed = 0
        for index, op in enumerate(operations):
            action = op.get("action") if isinstance(op, dict) else None
            method = BATCH_ACTIONS.get(action) if action else None
            if method is None:
                failed += 1
                results.append({"index": index, "success": False, "error": f"unknown action: {action}"})
                continue
            kwargs = {key: value for key, value in op.items() if key != "action"}
            try:
                method_fn = getattr(self, method)
                extra = {"actor": actor, "workspace": workspace}
                if "confirm" in _method_params(method_fn):
                    extra["confirm"] = confirm
                outcome = method_fn(**kwargs, **extra)
                outcome["index"] = index
                results.append(outcome)
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                failed += 1
                results.append({"index": index, "success": False, "error": str(exc)})

        payload = {
            "total": len(operations),
            "succeeded": len(results) - failed,
            "failed": failed,
            "results": results,
            "actor": actor,
        }
        self._record(EV_BATCH_COMPLETED, payload, workspace)
        return payload

    # ----------------------------------------------------------------------- #
    # Info / open / convenience
    # ----------------------------------------------------------------------- #
    def file_info(
        self,
        path: Any,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return metadata about a file or folder."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.FILE_INFO,
            source=target,
            actor=actor,
            workspace=workspace,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        info = target.stat()
        return {
            "path": str(target),
            "kind": "folder" if target.is_dir() else "file",
            "size": info.st_size,
            "modified": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
            "created": datetime.fromtimestamp(info.st_ctime).isoformat(timespec="seconds"),
            "readable": os.access(target, os.R_OK),
            "writable": os.access(target, os.W_OK),
        }

    def open_file(
        self,
        path: Any,
        *,
        actor: str = "user",
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open a file with the platform default application."""
        target = self._resolve(path)
        self._gate(
            FileOperationKind.OPEN_FILE,
            source=target,
            actor=actor,
            workspace=workspace,
        )
        if not target.exists():
            raise FileNotFoundError(target)
        opened = self._open_file(str(target))
        payload = {"path": str(target), "opened": opened, "actor": actor}
        self._record(EV_FILE_OPENED, payload, workspace)
        return payload

    def delete(
        self,
        path: Any,
        *,
        permanent: bool = False,
        recursive: bool = True,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Convenience: delete a file or folder (auto-detects the kind)."""
        target = self._resolve(path)
        if target.is_dir():
            return self.delete_folder(
                target,
                recursive=recursive,
                permanent=permanent,
                actor=actor,
                workspace=workspace,
                confirm=confirm,
            )
        return self.delete_file(
            target,
            permanent=permanent,
            actor=actor,
            workspace=workspace,
            confirm=confirm,
        )

    @staticmethod
    def _snippet(text: str, start: int, width: int) -> str:
        """Build a ``width``-char snippet around ``start``."""
        half = width // 2
        begin = max(0, start - half)
        end = min(len(text), start + half)
        prefix = "..." if begin > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[begin:end]}{suffix}"



def _method_params(fn) -> set:
    """Return the parameter names of a callable (for safe introspection)."""
    import inspect

    try:
        return set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return set()


#: batch operation action -> file manager method name
BATCH_ACTIONS = {
    "create_folder": "create_folder",
    "create_file": "create_file",
    "write_file": "write_file",
    "edit_file": "edit_file",
    "append_file": "append_file",
    "read_file": "read_file",
    "rename": "rename",
    "move": "move",
    "copy": "copy",
    "delete": "delete",
    "list": "list_directory",
    "replace_text": "replace_text",
    "file_info": "file_info",
}

