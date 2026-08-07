"""Tool actions for the File & Command Control System.

Exposes a family of tools to the main dispatcher (mirroring
``documents/action.py``): secure command execution, safe file operations,
workspace scanning and search. Services are resolved through the DI container
(auto-registering the subsystem on first use).

Every tool follows the host convention ``fn(parameters, player=None, speak=None)``
and returns a human-readable summary string. Permission denials are returned as
messages; confirmation-required operations return the token so the host can ask
the user and approve via :func:`confirm_operation`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.logging import get_logger

from automation.permissions import ConfirmationRequiredError, PermissionDeniedError

logger = get_logger("automation.action")

TOOL_RUN_COMMAND = "run_command"
TOOL_CREATE_FOLDER = "create_folder"
TOOL_CREATE_FILE = "create_file"
TOOL_READ_FILE = "read_file"
TOOL_WRITE_FILE = "write_file"
TOOL_EDIT_FILE = "edit_file"
TOOL_APPEND_FILE = "append_file"
TOOL_DELETE_FILE = "delete_file"
TOOL_LIST_DIRECTORY = "list_directory"
TOOL_SEARCH_FILES = "search_files"
TOOL_SCAN_WORKSPACE = "scan_workspace"
TOOL_FILE_INFO = "file_info"
TOOL_BATCH_FILE_OPS = "batch_file_ops"
TOOL_CONFIRM_OPERATION = "confirm_operation"
TOOL_RECENT_COMMANDS = "recent_commands"


def _object_schema(properties: Dict[str, Any], required: Optional[list] = None) -> Dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    TOOL_RUN_COMMAND: {
        "description": (
            "Run a command in the Lessan workspace. Safe, known commands run "
            "directly; dangerous or unknown commands require your confirmation. "
            "Never use to touch system paths outside the workspace."
        ),
        "parameters": _object_schema(
            {
                "command": {"type": "string", "description": "The command line to execute."},
                "cwd": {"type": "string", "description": "Working directory (inside the workspace)."},
                "timeout": {"type": "number", "description": "Timeout in seconds."},
                "shell": {"type": "boolean", "description": "Run through a shell (needs confirmation)."},
                "confirm": {"type": "boolean", "description": "Approve with a previously issued token."},
            },
            required=["command"],
        ),
    },
    TOOL_CREATE_FOLDER: {
        "description": "Create a folder (with parents) inside the workspace.",
        "parameters": _object_schema(
            {
                "path": {"type": "string", "description": "Folder path (relative to the workspace or absolute)."},
                "workspace": {"type": "string"},
            },
            required=["path"],
        ),
    },
    TOOL_CREATE_FILE: {
        "description": "Create a new file with optional content.",
        "parameters": _object_schema(
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "workspace": {"type": "string"},
            },
            required=["path"],
        ),
    },
    TOOL_READ_FILE: {
        "description": "Read a text file inside the workspace.",
        "parameters": _object_schema(
            {
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "description": "Cap on characters returned."},
                "workspace": {"type": "string"},
            },
            required=["path"],
        ),
    },
    TOOL_WRITE_FILE: {
        "description": "Overwrite a file with new content.",
        "parameters": _object_schema(
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "workspace": {"type": "string"},
            },
            required=["path", "content"],
        ),
    },
    TOOL_EDIT_FILE: {
        "description": "Replace text in a file (literal or regex).",
        "parameters": _object_schema(
            {
                "path": {"type": "string"},
                "old_text": {"type": "string", "description": "Text to find (omit to overwrite with new_text)."},
                "new_text": {"type": "string"},
                "count": {"type": "integer", "description": "Number of replacements (-1 = all)."},
                "regex": {"type": "boolean"},
                "workspace": {"type": "string"},
            },
            required=["path", "new_text"],
        ),
    },
    TOOL_APPEND_FILE: {
        "description": "Append content to a file (created if missing).",
        "parameters": _object_schema(
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "workspace": {"type": "string"},
            },
            required=["path", "content"],
        ),
    },
    TOOL_DELETE_FILE: {
        "description": "Delete a file or folder. Destructive — requires confirmation.",
        "parameters": _object_schema(
            {
                "path": {"type": "string"},
                "recursive": {"type": "boolean", "description": "Delete folders recursively."},
                "permanent": {"type": "boolean", "description": "Skip the .trash soft-delete."},
                "workspace": {"type": "string"},
            },
            required=["path"],
        ),
    },
    TOOL_LIST_DIRECTORY: {
        "description": "List a directory's entries inside the workspace.",
        "parameters": _object_schema(
            {"path": {"type": "string"}, "workspace": {"type": "string"}}
        ),
    },
    TOOL_SEARCH_FILES: {
        "description": "Search files by name, extension, path pattern or content.",
        "parameters": _object_schema(
            {
                "name": {"type": "string", "description": "fnmatch glob on the file name."},
                "extension": {"type": "string", "description": "e.g. py, md, txt."},
                "pattern": {"type": "string", "description": "Regex on the full path."},
                "content": {"type": "string", "description": "Substring of the file body."},
                "max_results": {"type": "integer"},
                "workspace": {"type": "string"},
            }
        ),
    },
    TOOL_SCAN_WORKSPACE: {
        "description": "Scan a workspace root and report counts, sizes and extensions.",
        "parameters": _object_schema(
            {
                "root": {"type": "string"},
                "max_depth": {"type": "integer"},
                "limit": {"type": "integer"},
                "workspace": {"type": "string"},
            }
        ),
    },
    TOOL_FILE_INFO: {
        "description": "Return metadata about a file or folder.",
        "parameters": _object_schema(
            {"path": {"type": "string"}, "workspace": {"type": "string"}},
            required=["path"],
        ),
    },
    TOOL_BATCH_FILE_OPS: {
        "description": "Run a list of file operations in order.",
        "parameters": _object_schema(
            {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "description": "Each operation: {action: create_file|write_file|read_file|edit_file|rename|move|copy|delete|create_folder|list|replace_text, ...params}",
                    },
                },
                "workspace": {"type": "string"},
            },
            required=["operations"],
        ),
    },
    TOOL_CONFIRM_OPERATION: {
        "description": "Approve a pending dangerous operation using its token.",
        "parameters": _object_schema(
            {"token": {"type": "string"}}, required=["token"]
        ),
    },
    TOOL_RECENT_COMMANDS: {
        "description": "List the most recent command executions.",
        "parameters": _object_schema({"limit": {"type": "integer"}}),
    },
}


# --------------------------------------------------------------------------- #
# Tool entry points (host convention: fn(parameters, player, speak))
# --------------------------------------------------------------------------- #
def run_command(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    """Execute a command through the secure :class:`CommandExecutor`."""
    parameters = parameters or {}
    command = (parameters.get("command") or "").strip()
    if not command:
        return "No command provided."
    executor = _services().executor
    try:
        result = executor.run(
            command,
            cwd=parameters.get("cwd"),
            timeout=parameters.get("timeout"),
            shell=bool(parameters.get("shell", False)),
            actor="agent",
            confirm=bool(parameters.get("confirm", False)),
        )
    except ConfirmationRequiredError as exc:
        return _confirmation_message(exc)
    except PermissionDeniedError as exc:
        return f"⛔ Denied: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"❌ Could not run command: {exc}"
    return _command_summary(result)


def create_folder(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.create_folder(
            parameters["path"], actor="agent", workspace=parameters.get("workspace")
        )
        return f"📁 Folder created: {payload['path']}"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def create_file(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.create_file(
            parameters["path"],
            content=parameters.get("content") or "",
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        return f"📄 File created: {payload['path']} ({payload['bytes']} bytes)"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def read_file(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.read_file(
            parameters["path"],
            max_chars=parameters.get("max_chars"),
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        return payload.get("content") or "(empty file)"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def write_file(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.write_file(
            parameters["path"],
            parameters.get("content") or "",
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        return f"✍️ File written: {payload['path']} ({payload['bytes']} bytes)"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def edit_file(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.edit_file(
            parameters["path"],
            old_text=parameters.get("old_text"),
            new_text=parameters.get("new_text"),
            count=parameters.get("count", 1),
            regex=bool(parameters.get("regex", False)),
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        return f"🔧 Edited {payload['path']}: {payload['replaced']} replacement(s)"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def append_file(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.append_file(
            parameters["path"],
            parameters.get("content") or "",
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        return f"➕ Appended to {payload['path']} (now {payload['size']} bytes)"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def delete_file(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.delete(
            parameters["path"],
            recursive=bool(parameters.get("recursive", True)),
            permanent=bool(parameters.get("permanent", False)),
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        return f"🗑️ Deleted {payload['path']}"
    except ConfirmationRequiredError as exc:
        return _confirmation_message(exc)
    except PermissionDeniedError as exc:
        return f"⛔ Denied: {exc}"
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def list_directory(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.list_directory(
            parameters.get("path"), actor="agent", workspace=parameters.get("workspace")
        )
        lines = [f"📂 {payload['path']} ({payload['count']} entries)"]
        for entry in payload["entries"]:
            kind = "📁" if entry["kind"] == "folder" else "📄"
            size = f" {entry['size']}B" if entry["size"] is not None else ""
            lines.append(f"  {kind} {entry['name']}{size}")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def search_files(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        payload = _services().files.search_files(
            name=parameters.get("name"),
            extension=parameters.get("extension"),
            pattern=parameters.get("pattern"),
            content=parameters.get("content"),
            max_results=parameters.get("max_results", 50),
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        if not payload["count"]:
            return "No files matched."
        lines = [f"🔎 {payload['count']} match(es) under {payload['root']}:"]
        for match in payload["matches"]:
            line = f"  {match['path']}"
            if match.get("snippet"):
                line += f"\n    …{match['snippet']}…"
            lines.append(line)
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def scan_workspace(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        summary = _services().scanner.scan(
            parameters.get("root"),
            max_depth=parameters.get("max_depth"),
            limit=parameters.get("limit"),
            actor="agent",
            workspace=parameters.get("workspace"),
        )
        lines = [
            f"🧭 Workspace scan of {summary.root} in {summary.duration_ms:.0f}ms",
            f"  Files: {summary.file_count} · Folders: {summary.dir_count}",
            f"  Total size: {_human_bytes(summary.total_bytes)}",
            f"  Extensions: {dict(summary.extensions)}",
        ]
        if summary.largest:
            top = ", ".join(
                f"{m['name']} ({_human_bytes(m['size'])})" for m in summary.largest[:3]
            )
            lines.append(f"  Largest: {top}")
        if summary.truncated:
            lines.append("  ⚠️ truncated (limit reached)")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def file_info(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    try:
        info = _services().files.file_info(
            parameters["path"], actor="agent", workspace=parameters.get("workspace")
        )
        return (
            f"ℹ️ {info['path']}\n"
            f"  kind: {info['kind']} · size: {info['size']} bytes\n"
            f"  modified: {info['modified']} · created: {info['created']}\n"
            f"  readable: {info['readable']} · writable: {info['writable']}"
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def batch_file_ops(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    operations = parameters.get("operations") or []
    if not isinstance(operations, list) or not operations:
        return "batch_file_ops requires a non-empty 'operations' list."
    try:
        payload = _services().files.batch(
            operations, actor="agent", workspace=parameters.get("workspace")
        )
        lines = [
            f"⚙️ Batch: {payload['succeeded']}/{payload['total']} succeeded, "
            f"{payload['failed']} failed"
        ]
        for result in payload["results"]:
            if result.get("success"):
                lines.append(f"  ✅ [{result.get('index')}] {result.get('path', 'op')}")
            else:
                lines.append(f"  ❌ [{result.get('index')}] {result.get('error')}")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def confirm_operation(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    token = parameters.get("token")
    if not token:
        return "confirm_operation requires a 'token'."
    if _services().permissions.confirm(token, actor="user"):
        return "✅ Operation confirmed and approved."
    return "❌ Token is invalid or expired."


def recent_commands(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    parameters = parameters or {}
    records = _services().executor.history.recent(limit=parameters.get("limit", 10))
    if not records:
        return "No command history yet."
    lines = ["🕘 Recent commands:"]
    for record in records:
        lines.append(f"  {record['started_at']} [{record['returncode']}] {record['command']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Service resolution + formatting helpers
# --------------------------------------------------------------------------- #
class _Services:
    """Lazily resolved automation services."""

    def __init__(self) -> None:
        self._files = None
        self._executor = None
        self._scanner = None
        self._permissions = None

    @property
    def files(self):
        if self._files is None:
            from automation.file_manager import WorkspaceFileManager

            self._files = _container().resolve(WorkspaceFileManager)
        return self._files

    @property
    def executor(self):
        if self._executor is None:
            from automation.command_executor import CommandExecutor

            self._executor = _container().resolve(CommandExecutor)
        return self._executor

    @property
    def scanner(self):
        if self._scanner is None:
            from automation.scanner import WorkspaceScanner

            self._scanner = _container().resolve(WorkspaceScanner)
        return self._scanner

    @property
    def permissions(self):
        if self._permissions is None:
            from automation.permissions import PermissionManager

            self._permissions = _container().resolve(PermissionManager)
        return self._permissions


_services_instance = _Services()


def _services() -> _Services:
    return _services_instance


def _container():
    from core.di.container import container

    from automation.di import register_automation_system

    register_automation_system(container)
    return container


def _command_summary(result) -> str:
    lines = [f"💻 {result.summary()}"]
    if result.stdout.strip():
        lines.append(result.stdout.rstrip())
    if result.stderr.strip():
        lines.append(f"stderr:\n{result.stderr.rstrip()}")
    return "\n".join(lines)


def _confirmation_message(exc) -> str:
    token = getattr(exc, "token", None)
    message = f"⚠️ {exc}"
    if token:
        message += f"\nApprove with the confirm_operation tool using token: {token}"
    return message


def _error(exc) -> str:
    if isinstance(exc, ConfirmationRequiredError):
        return _confirmation_message(exc)
    if isinstance(exc, PermissionDeniedError):
        return f"⛔ Denied: {exc}"
    return f"❌ {exc}"


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def automation_tools():
    """Return the list of host-dispatched :class:`AutomationTool` entries."""
    from automation.interfaces import automation_tool

    handlers = {
        TOOL_RUN_COMMAND: run_command,
        TOOL_CREATE_FOLDER: create_folder,
        TOOL_CREATE_FILE: create_file,
        TOOL_READ_FILE: read_file,
        TOOL_WRITE_FILE: write_file,
        TOOL_EDIT_FILE: edit_file,
        TOOL_APPEND_FILE: append_file,
        TOOL_DELETE_FILE: delete_file,
        TOOL_LIST_DIRECTORY: list_directory,
        TOOL_SEARCH_FILES: search_files,
        TOOL_SCAN_WORKSPACE: scan_workspace,
        TOOL_FILE_INFO: file_info,
        TOOL_BATCH_FILE_OPS: batch_file_ops,
        TOOL_CONFIRM_OPERATION: confirm_operation,
        TOOL_RECENT_COMMANDS: recent_commands,
    }
    tools = []
    for name, handler in handlers.items():
        schema = TOOL_SCHEMAS.get(name, {})
        tools.append(
            automation_tool(
                name,
                schema.get("description", ""),
                handler,
                schema.get("parameters"),
            )
        )
    return tools



