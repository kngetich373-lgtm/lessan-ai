"""AutomationAgent — exposes the File & Command Control System as a
Lessan AI agent with capabilities covering file management, command
execution, workspace scanning and watcher control.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.framework.agent_registry import agent_registry
from agents.framework.base_agent import AgentTask, BaseAgent
from core.logging import get_logger

logger = get_logger("automation.agent")


@agent_registry.register
class AutomationAgent(BaseAgent):
    """Manages workspace files, commands, scanning and watching for Lessan AI."""

    name = "file_command_control"
    display_name = "File & Command Control"
    description = (
        "Safe file operations, secure command execution, workspace "
        "scanning/searching, and filesystem watching — all constrained "
        "by a security policy that blocks system paths and requires "
        "confirmation for destructive operations."
    )
    icon = "🛠️"
    color = "#f59e0b"

    def __init__(
        self,
        file_manager=None,
        command_executor=None,
        scanner=None,
        watcher=None,
    ) -> None:
        super().__init__()
        self._files = file_manager
        self._executor = command_executor
        self._scanner = scanner
        self._watcher = watcher

    def on_initialize(self, config: Dict[str, Any]) -> None:
        if self._files is None or self._executor is None:
            _auto_resolve(self)
        self._register_caps()

    def _register_caps(self) -> None:
        self.register_capability(
            "list_directory",
            "List a directory's entries inside the workspace.",
            self._cap_list_directory,
            {"path": {"type": "string"}},
        )
        self.register_capability(
            "create_folder",
            "Create a folder (with parents) inside the workspace.",
            self._cap_create_folder,
            {"path": {"type": "string"}},
        )
        self.register_capability(
            "create_file",
            "Create a new file with optional content.",
            self._cap_create_file,
            {"path": {"type": "string"}, "content": {"type": "string"}},
        )
        self.register_capability(
            "read_file",
            "Read a text file inside the workspace.",
            self._cap_read_file,
            {"path": {"type": "string"}, "max_chars": {"type": "integer"}},
        )
        self.register_capability(
            "write_file",
            "Overwrite a file with new content.",
            self._cap_write_file,
            {"path": {"type": "string"}, "content": {"type": "string"}},
        )
        self.register_capability(
            "edit_file",
            "Replace text in a file.",
            self._cap_edit_file,
            {"path": {"type": "string"}, "old_text": {"type": "string"},
             "new_text": {"type": "string"}},
        )
        self.register_capability(
            "append_file",
            "Append content to a file.",
            self._cap_append_file,
            {"path": {"type": "string"}, "content": {"type": "string"}},
        )
        self.register_capability(
            "rename_file",
            "Rename or move a file/folder.",
            self._cap_rename,
            {"source": {"type": "string"}, "destination": {"type": "string"}},
        )
        self.register_capability(
            "delete_file",
            "Delete a file or folder (requires confirmation).",
            self._cap_delete,
            {"path": {"type": "string"}, "recursive": {"type": "boolean"}},
        )
        self.register_capability(
            "search_files",
            "Search files by name, extension, pattern or content.",
            self._cap_search,
            {"name": {"type": "string"}, "extension": {"type": "string"},
             "content": {"type": "string"}, "max_results": {"type": "integer"}},
        )
        self.register_capability(
            "scan_workspace",
            "Scan a workspace root and report a summary.",
            self._cap_scan,
            {"root": {"type": "string"}, "max_depth": {"type": "integer"},
             "limit": {"type": "integer"}},
        )
        self.register_capability(
            "file_info",
            "Return metadata about a file or folder.",
            self._cap_file_info,
            {"path": {"type": "string"}},
        )
        self.register_capability(
            "run_command",
            "Run a command inside the workspace with security checks.",
            self._cap_run_command,
            {"command": {"type": "string"}, "cwd": {"type": "string"},
             "timeout": {"type": "number"}},
        )
        self.register_capability(
            "confirm_operation",
            "Approve a pending dangerous operation with its token.",
            self._cap_confirm,
            {"token": {"type": "string"}},
        )
        self.register_capability(
            "recent_command_history",
            "List recent command executions.",
            self._cap_history,
            {"limit": {"type": "integer"}},
        )

    # ------------------------------------------------------------------ #
    # Capability handlers
    # ------------------------------------------------------------------ #
    def _cap_list_directory(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.list_directory(kwargs.get("path"), actor="agent")

    def _cap_create_folder(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.create_folder(kwargs["path"], actor="agent")

    def _cap_create_file(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.create_file(
            kwargs["path"], content=kwargs.get("content") or "", actor="agent"
        )

    def _cap_read_file(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.read_file(
            kwargs["path"], max_chars=kwargs.get("max_chars"), actor="agent"
        )

    def _cap_write_file(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.write_file(
            kwargs["path"], kwargs.get("content") or "", actor="agent"
        )

    def _cap_edit_file(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.edit_file(
            kwargs["path"],
            old_text=kwargs.get("old_text"),
            new_text=kwargs.get("new_text"),
            actor="agent",
        )

    def _cap_append_file(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.append_file(
            kwargs["path"], kwargs.get("content") or "", actor="agent"
        )

    def _cap_rename(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.rename(
            kwargs["source"], kwargs["destination"], actor="agent"
        )

    def _cap_delete(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.delete(
            kwargs["path"],
            recursive=bool(kwargs.get("recursive", True)),
            actor="agent",
        )

    def _cap_search(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.search_files(
            name=kwargs.get("name"),
            extension=kwargs.get("extension"),
            content=kwargs.get("content"),
            max_results=kwargs.get("max_results", 50),
            actor="agent",
        )

    def _cap_scan(self, **kwargs: Any) -> Dict[str, Any]:
        summary = self._scanner.scan(
            kwargs.get("root"),
            max_depth=kwargs.get("max_depth"),
            limit=kwargs.get("limit"),
            actor="agent",
        )
        return summary.as_dict()

    def _cap_file_info(self, **kwargs: Any) -> Dict[str, Any]:
        return self._files.file_info(kwargs["path"], actor="agent")

    def _cap_run_command(self, **kwargs: Any) -> Dict[str, Any]:
        return self._executor.run(
            kwargs["command"],
            cwd=kwargs.get("cwd"),
            timeout=kwargs.get("timeout"),
            actor="agent",
        ).as_dict()

    def _cap_confirm(self, **kwargs: Any) -> Dict[str, Any]:
        token = kwargs.get("token")
        if not token:
            return {"approved": False, "error": "missing token"}
        return {"approved": self._files.permissions.confirm(token, actor="user")}

    def _cap_history(self, **kwargs: Any) -> Dict[str, Any]:
        return {"commands": self._executor.history.recent(limit=kwargs.get("limit", 10))}

    def on_run(self, task: AgentTask) -> Any:
        desc = (task.description or "").strip().lower()
        if desc.startswith(("list", "show", "read", "open")):
            return "Use the 'list_directory', 'read_file' or 'file_info' capabilities."
        if desc.startswith(("create", "make", "write", "edit", "append")):
            return "Use 'create_file', 'write_file', 'edit_file' or 'append_file'."
        if desc.startswith(("run", "execute", "terminal")):
            return "Use the 'run_command' capability."
        if "search" in desc or "find" in desc:
            return "Use the 'search_files' or 'scan_workspace' capabilities."
        return self.description


def _auto_resolve(agent: AutomationAgent) -> None:
    """Resolve services from the DI container (registering the system)."""
    try:
        from core.di.container import container

        from automation.command_executor import CommandExecutor
        from automation.di import register_automation_system
        from automation.file_manager import WorkspaceFileManager
        from automation.scanner import WorkspaceScanner
        from automation.watcher import FileWatcher

        register_automation_system(container)
        agent._files = container.resolve(WorkspaceFileManager)
        agent._executor = container.resolve(CommandExecutor)
        agent._scanner = container.resolve(WorkspaceScanner)
        agent._watcher = container.resolve(FileWatcher)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not resolve automation services: {exc}")


def register_automation_agent(manager=None):
    """Register and spawn the AutomationAgent.

    Args:
        manager: The agent manager. When None, ``agents.framework.agent_manager``
            is used. The agent type is registered via the ``@agent_registry.register``
            decorator, so spawning only needs the type name.
    """
    try:
        from agents.framework.agent_manager import agent_manager

        manager = manager or agent_manager
        return manager.spawn(AutomationAgent.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not spawn AutomationAgent: {exc}")
        try:
            return agent_registry.get_or_create(AutomationAgent.name)
        except Exception as inner:  # noqa: BLE001
            logger.warning(f"Could not create AutomationAgent: {inner}")
            return AutomationAgent()



