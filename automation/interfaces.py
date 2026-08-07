"""Capability contracts for the File & Command Control System.

Subsystems should depend on these structural interfaces rather than concrete
implementations so the DI container can swap or mock them. :class:`AutomationTool`
describes a tool the host dispatcher can register (mirrors ``documents.action``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from typing import Protocol, runtime_checkable


@dataclass
class AutomationTool:
    """Metadata + handler for a host-dispatched automation tool."""

    name: str
    description: str
    handler: Callable[..., Any]
    schema: Dict[str, Any] = field(default_factory=dict)


def automation_tool(
    name: str,
    description: str,
    handler: Callable[..., Any],
    schema: Optional[Dict[str, Any]] = None,
) -> AutomationTool:
    """Build an :class:`AutomationTool` with a JSON-schema parameters block."""
    return AutomationTool(
        name=name,
        description=description,
        handler=handler,
        schema=schema or {"type": "object", "properties": {}, "required": []},
    )


@runtime_checkable
class IPermissionManager(Protocol):
    """Permission enforcement contract (see ``automation.permissions``)."""

    def check(self, action: Any, *, source: Any = None, destination: Any = None,
              actor: str = "user", command: Optional[str] = None, cwd: Any = None,
              shell: bool = False, recursive: bool = False,
              workspace: Optional[str] = None,
              auto_confirm: Optional[bool] = None) -> Any: ...

    def confirm(self, token: Optional[str], actor: str = "user") -> bool: ...

    def revoke(self, token: Optional[str]) -> bool: ...

    def pending(self) -> List[Dict[str, Any]]: ...

    def audit(self, limit: int = 100) -> List[Dict[str, Any]]: ...

    def register_workspace(self, root: Any, *, name: Optional[str] = None,
                           allowed: bool = True) -> Any: ...

    def allow_path(self, path: Any) -> Any: ...


@runtime_checkable
class IFileManager(Protocol):
    """Safe workspace file/folder operations (see ``automation.file_manager``)."""

    def create_folder(self, path: Any, *, actor: str = "user",
                      workspace: Optional[str] = None,
                      confirm: bool = False) -> Dict[str, Any]: ...

    def rename(self, source: Any, destination: Any, *, actor: str = "user",
               workspace: Optional[str] = None,
               confirm: bool = False) -> Dict[str, Any]: ...

    def move(self, source: Any, destination: Any, *, actor: str = "user",
             workspace: Optional[str] = None,
             confirm: bool = False) -> Dict[str, Any]: ...

    def copy(self, source: Any, destination: Any, *, actor: str = "user",
             workspace: Optional[str] = None,
             confirm: bool = False) -> Dict[str, Any]: ...

    def delete_file(self, path: Any, *, permanent: bool = False,
                    actor: str = "user", workspace: Optional[str] = None,
                    confirm: bool = False) -> Dict[str, Any]: ...

    def delete_folder(self, path: Any, *, recursive: bool = True,
                      permanent: bool = False, actor: str = "user",
                      workspace: Optional[str] = None,
                      confirm: bool = False) -> Dict[str, Any]: ...

    def list_directory(self, path: Any = None, *, actor: str = "user",
                       workspace: Optional[str] = None) -> Dict[str, Any]: ...

    def create_file(self, path: Any, content: str = "", *, actor: str = "user",
                    workspace: Optional[str] = None,
                    confirm: bool = False) -> Dict[str, Any]: ...

    def read_file(self, path: Any, *, max_chars: Optional[int] = None,
                  actor: str = "user",
                  workspace: Optional[str] = None) -> Dict[str, Any]: ...

    def write_file(self, path: Any, content: str, *, actor: str = "user",
                   workspace: Optional[str] = None,
                   confirm: bool = False) -> Dict[str, Any]: ...

    def edit_file(self, path: Any, old_text: Optional[str] = None,
                  new_text: Optional[str] = None, *, count: int = 1,
                  regex: bool = False, actor: str = "user",
                  workspace: Optional[str] = None,
                  confirm: bool = False) -> Dict[str, Any]: ...

    def search_files(self, *, root: Any = None, name: Optional[str] = None,
                     extension: Optional[str] = None,
                     pattern: Optional[str] = None,
                     content: Optional[str] = None, regex: bool = False,
                     max_results: int = 100, recursive: bool = True,
                     actor: str = "user",
                     workspace: Optional[str] = None) -> Dict[str, Any]: ...

    def replace_text(self, source: Any, old_text: str, new_text: str, *,
                     regex: bool = False, count: int = -1,
                     recursive: bool = False, actor: str = "user",
                     workspace: Optional[str] = None,
                     confirm: bool = False) -> Dict[str, Any]: ...

    def file_info(self, path: Any, *, actor: str = "user",
                  workspace: Optional[str] = None) -> Dict[str, Any]: ...

    def batch(self, operations: List[Dict[str, Any]], *, actor: str = "user",
              workspace: Optional[str] = None,
              confirm: bool = False) -> Dict[str, Any]: ...


@runtime_checkable
class ICommandExecutor(Protocol):
    """Secure command execution (see ``automation.command_executor``)."""

    def run(self, command: str, *, cwd: Any = None, timeout: Optional[float] = None,
            shell: bool = False, actor: str = "user",
            workspace: Optional[str] = None, confirm: bool = False,
            env: Optional[Dict[str, str]] = None,
            stream: Any = None) -> Any: ...

    def run_async(self, command: str, *, cwd: Any = None,
                  timeout: Optional[float] = None, shell: bool = False,
                  actor: str = "user", workspace: Optional[str] = None,
                  confirm: bool = False,
                  env: Optional[Dict[str, str]] = None) -> Any: ...

    def cancel(self, command_prefix: Optional[str] = None) -> int: ...

    def stop_all(self) -> int: ...

    @property
    def history(self) -> Any: ...

    @property
    def registry(self) -> Any: ...


@runtime_checkable
class IWorkspaceScanner(Protocol):
    """Read-only workspace walking and search (see ``automation.scanner``)."""

    def scan(self, root: Any = None, *, patterns: Optional[List[str]] = None,
             ignore: Optional[List[str]] = None, max_depth: Optional[int] = None,
             limit: Optional[int] = None, skip_protected: bool = True,
             actor: str = "user",
             workspace: Optional[str] = None) -> Any: ...

    def find_files(self, *, root: Any = None, query: Optional[str] = None,
                   name: Optional[str] = None, extension: Optional[str] = None,
                   pattern: Optional[str] = None,
                   content: Optional[str] = None, max_results: int = 100,
                   snippet: bool = True, actor: str = "user",
                   workspace: Optional[str] = None) -> Dict[str, Any]: ...


@runtime_checkable
class IFileWatcher(Protocol):
    """Polling filesystem watcher (see ``automation.watcher``)."""

    def start(self, root: Any = None, *, interval: Optional[float] = None,
              patterns: Optional[List[str]] = None,
              actor: str = "user") -> Any: ...

    def stop(self, join: bool = True) -> None: ...

    def snapshot(self) -> List[Dict[str, Any]]: ...

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]: ...

    @property
    def running(self) -> bool: ...

