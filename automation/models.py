"""Value models for the File & Command Control System.

Shared value objects used across the subsystem:

- :class:`ExecutionResult` — the outcome of one command execution
- :class:`FileOperation` — a recorded file/folder mutation
- :class:`PermissionDecision` — the result of a security check
- :class:`CommandReview` — the security assessment of a command
- :class:`WorkspaceProfile` — an approved workspace sandbox
- :class:`FileMatch` — one file search result
- :class:`CommandSpec` — a registered command definition
- :class:`ScanSummary` — the result of a workspace scan
- :class:`WatcherEvent` — a filesystem change observed by the watcher
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DangerLevel(str, Enum):
    """Severity of an operation for permission decisions."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FileOperationKind(str, Enum):
    """Every operation kind the File & Command Control System supports."""

    CREATE_FOLDER = "create_folder"
    RENAME_FOLDER = "rename_folder"
    MOVE_FOLDER = "move_folder"
    COPY_FOLDER = "copy_folder"
    DELETE_FOLDER = "delete_folder"
    LIST_DIRECTORY = "list_directory"
    SCAN_WORKSPACE = "scan_workspace"
    CREATE_FILE = "create_file"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    APPEND_FILE = "append_file"
    RENAME_FILE = "rename_file"
    COPY_FILE = "copy_file"
    MOVE_FILE = "move_file"
    DELETE_FILE = "delete_file"
    SEARCH_FILES = "search_files"
    REPLACE_TEXT = "replace_text"
    OPEN_FILE = "open_file"
    FILE_INFO = "file_info"
    BATCH = "batch"
    EXECUTE_COMMAND = "execute_command"


#: Operations that mutate or destroy workspace content.
DESTRUCTIVE_KINDS = frozenset(
    {
        FileOperationKind.DELETE_FILE,
        FileOperationKind.DELETE_FOLDER,
        FileOperationKind.MOVE_FILE,
        FileOperationKind.MOVE_FOLDER,
        FileOperationKind.RENAME_FILE,
        FileOperationKind.RENAME_FOLDER,
        FileOperationKind.WRITE_FILE,
        FileOperationKind.EDIT_FILE,
        FileOperationKind.REPLACE_TEXT,
    }
)

#: Danger level of each file operation kind. The permission manager uses
#: these to decide when explicit user confirmation is required.
KIND_DANGER: Dict[FileOperationKind, DangerLevel] = {
    FileOperationKind.CREATE_FOLDER: DangerLevel.SAFE,
    FileOperationKind.CREATE_FILE: DangerLevel.SAFE,
    FileOperationKind.READ_FILE: DangerLevel.SAFE,
    FileOperationKind.LIST_DIRECTORY: DangerLevel.SAFE,
    FileOperationKind.SEARCH_FILES: DangerLevel.SAFE,
    FileOperationKind.SCAN_WORKSPACE: DangerLevel.SAFE,
    FileOperationKind.OPEN_FILE: DangerLevel.SAFE,
    FileOperationKind.FILE_INFO: DangerLevel.SAFE,
    FileOperationKind.COPY_FILE: DangerLevel.LOW,
    FileOperationKind.COPY_FOLDER: DangerLevel.LOW,
    FileOperationKind.APPEND_FILE: DangerLevel.MEDIUM,
    FileOperationKind.WRITE_FILE: DangerLevel.MEDIUM,
    FileOperationKind.EDIT_FILE: DangerLevel.MEDIUM,
    FileOperationKind.REPLACE_TEXT: DangerLevel.MEDIUM,
    FileOperationKind.RENAME_FILE: DangerLevel.MEDIUM,
    FileOperationKind.RENAME_FOLDER: DangerLevel.MEDIUM,
    FileOperationKind.MOVE_FILE: DangerLevel.MEDIUM,
    FileOperationKind.MOVE_FOLDER: DangerLevel.MEDIUM,
    FileOperationKind.DELETE_FILE: DangerLevel.HIGH,
    FileOperationKind.DELETE_FOLDER: DangerLevel.CRITICAL,
    FileOperationKind.BATCH: DangerLevel.HIGH,
    FileOperationKind.EXECUTE_COMMAND: DangerLevel.MEDIUM,
}


@dataclass
class ExecutionResult:
    """Outcome of a single command execution."""

    command: str
    argv: List[str] = field(default_factory=list)
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    cancelled: bool = False
    cwd: str = ""
    shell: bool = False
    started_at: str = ""
    completed_at: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.cancelled

    def as_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 2),
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "cwd": self.cwd,
            "shell": self.shell,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
        }

    def summary(self) -> str:
        if self.timed_out:
            status = "TIMEOUT"
        elif self.cancelled:
            status = "CANCELLED"
        elif self.success:
            status = "OK"
        else:
            status = f"FAILED(exit={self.returncode})"
        return f"[{status}] {self.command!r} in {self.duration_ms:.0f}ms"

    def __str__(self) -> str:
        return self.summary()


@dataclass
class FileOperation:
    """A recorded file/folder mutation."""

    kind: FileOperationKind
    source: Optional[str] = None
    destination: Optional[str] = None
    actor: str = "user"
    workspace: Optional[str] = None
    success: bool = True
    detail: Optional[str] = None
    performed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source": self.source,
            "destination": self.destination,
            "actor": self.actor,
            "workspace": self.workspace,
            "success": self.success,
            "detail": self.detail,
            "performed_at": self.performed_at,
        }


@dataclass
class CommandReview:
    """Security assessment of a command string."""

    danger_level: DangerLevel
    reason: str
    always_deny: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "danger_level": self.danger_level.value,
            "reason": self.reason,
            "always_deny": self.always_deny,
        }


@dataclass
class PermissionDecision:
    """The result of a permission check for one operation."""

    action: str
    actor: str
    allowed: bool = False
    requires_confirmation: bool = False
    reason: str = ""
    danger_level: DangerLevel = DangerLevel.MEDIUM
    source: Optional[str] = None
    destination: Optional[str] = None
    command: Optional[str] = None
    workspace: Optional[str] = None
    token: Optional[str] = None
    expires_at: Optional[float] = None
    confirmed: bool = False
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "actor": self.actor,
            "allowed": self.allowed,
            "requires_confirmation": self.requires_confirmation,
            "reason": self.reason,
            "danger_level": self.danger_level.value,
            "source": self.source,
            "destination": self.destination,
            "command": self.command,
            "workspace": self.workspace,
            "token": self.token,
            "expires_at": self.expires_at,
            "confirmed": self.confirmed,
            "checked_at": self.checked_at,
        }


@dataclass
class WorkspaceProfile:
    """An approved workspace sandbox.

    ``allowed`` controls whether the root is writable/executable. When
    ``False`` the root is readable but cannot be modified (read-only mode).
    """

    name: str
    root: Path
    allowed: bool = True
    tags: tuple = field(default_factory=tuple)

    def contains(self, path: Path) -> bool:
        resolved = Path(path).resolve()
        root = self.root.resolve()
        return resolved == root or root in resolved.parents

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "root": str(self.root),
            "allowed": self.allowed,
            "tags": list(self.tags),
        }


@dataclass
class FileMatch:
    """One file search result."""

    path: str
    name: str
    kind: str = "file"  # file | dir
    size: Optional[int] = None
    modified: Optional[str] = None
    snippet: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "kind": self.kind,
            "size": self.size,
            "modified": self.modified,
            "snippet": self.snippet,
        }


@dataclass
class CommandSpec:
    """A registered, policy-reviewed command definition."""

    name: str
    description: str
    binary: str
    danger_level: DangerLevel = DangerLevel.LOW

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "binary": self.binary,
            "danger_level": self.danger_level.value,
        }


@dataclass
class ScanSummary:
    """The result of a workspace scan."""

    root: str
    file_count: int = 0
    dir_count: int = 0
    total_bytes: int = 0
    largest: List[Dict[str, Any]] = field(default_factory=list)
    newest: List[Dict[str, Any]] = field(default_factory=list)
    extensions: Dict[str, int] = field(default_factory=dict)
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    duration_ms: float = 0.0
    truncated: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "file_count": self.file_count,
            "dir_count": self.dir_count,
            "total_bytes": self.total_bytes,
            "largest": self.largest,
            "newest": self.newest,
            "extensions": self.extensions,
            "scanned_at": self.scanned_at,
            "duration_ms": round(self.duration_ms, 2),
            "truncated": self.truncated,
        }


@dataclass
class WatcherEvent:
    """A filesystem change observed by the FileWatcher."""

    event_type: str  # created | modified | deleted
    path: str
    is_dir: bool = False
    size: Optional[int] = None
    modified: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
            "modified": self.modified,
        }

