"""File & Command Control System for Lessan AI.

Safe file operations, secure command execution, permission enforcement,
workspace scanning/searching and filesystem watching — all constrained by a
central :class:`SecurityPolicy` that blocks system-critical paths, enforces
workspace containment and requires expiring confirmation tokens for
destructive operations.

Quick start (standalone):

    >>> from automation import SecurityPolicy, PermissionManager, WorkspaceFileManager
    >>> policy = SecurityPolicy(workspace_roots=["~/Desktop"])
    >>> permissions = PermissionManager(policy)
    >>> files = WorkspaceFileManager(permissions)
    >>> files.create_file("notes.txt", content="hello")
"""

from automation.command_executor import (
    CommandExecutor,
    CommandHistory,
    CommandRegistry,
)
from automation.di import register_automation_system, unregister_automation_system
from automation.events import (
    ALL_AUTOMATION_EVENTS,
    EV_BATCH_COMPLETED,
    EV_COMMAND_COMPLETED,
    EV_COMMAND_FAILED,
    EV_COMMAND_STARTED,
    EV_FILE_COPIED,
    EV_FILE_CREATED,
    EV_FILE_DELETED,
    EV_FILE_MODIFIED,
    EV_FILE_MOVED,
    EV_FILE_OPENED,
    EV_FILE_RENAMED,
    EV_FOLDER_CREATED,
    EV_FOLDER_DELETED,
    EV_PERMISSION_CHECKED,
    EV_PERMISSION_CONFIRMED,
    EV_PERMISSION_DENIED,
    EV_SCAN_COMPLETED,
    EV_WATCH_EVENT,
    emit_automation_event,
)
from automation.file_manager import WorkspaceFileManager
from automation.models import (
    CommandReview,
    CommandSpec,
    DangerLevel,
    ExecutionResult,
    FileMatch,
    FileOperation,
    FileOperationKind,
    PermissionDecision,
    ScanSummary,
    WatcherEvent,
    WorkspaceProfile,
)
from automation.permissions import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    PermissionManager,
)
from automation.scanner import WorkspaceScanner
from automation.security import SecurityPolicy
from automation.watcher import FileWatcher
from automation.workflow import (
    ACTION_CREATE_FILE,
    ACTION_EDIT_FILE,
    ACTION_LIST_DIRECTORY,
    ACTION_READ_FILE,
    ACTION_RUN_COMMAND,
    ACTION_SCAN,
    ACTION_SEARCH,
    ACTION_WRITE_FILE,
    ALL_AUTOMATION_ACTIONS,
    AutomationCommandWorkflow,
    AutomationFileOpsWorkflow,
    AutomationScanWorkflow,
    WORKFLOW_COMMAND,
    WORKFLOW_FILE_OPS,
    WORKFLOW_SCAN,
    build_command_workflow,
    build_file_ops_workflow,
    build_scan_workflow,
    register_automation_workflows,
)

#: Subsystem version.
__version__ = "1.0.0"

__all__ = [
    "ACTION_CREATE_FILE",
    "ACTION_EDIT_FILE",
    "ACTION_LIST_DIRECTORY",
    "ACTION_READ_FILE",
    "ACTION_RUN_COMMAND",
    "ACTION_SCAN",
    "ACTION_SEARCH",
    "ACTION_WRITE_FILE",
    "ALL_AUTOMATION_ACTIONS",
    "ALL_AUTOMATION_EVENTS",
    "AutomationCommandWorkflow",
    "AutomationFileOpsWorkflow",
    "AutomationScanWorkflow",
    "CommandExecutor",
    "CommandHistory",
    "CommandRegistry",
    "CommandReview",
    "CommandSpec",
    "ConfirmationRequiredError",
    "DangerLevel",
    "EV_BATCH_COMPLETED",
    "EV_COMMAND_COMPLETED",
    "EV_COMMAND_FAILED",
    "EV_COMMAND_STARTED",
    "EV_FILE_COPIED",
    "EV_FILE_CREATED",
    "EV_FILE_DELETED",
    "EV_FILE_MODIFIED",
    "EV_FILE_MOVED",
    "EV_FILE_OPENED",
    "EV_FILE_RENAMED",
    "EV_FOLDER_CREATED",
    "EV_FOLDER_DELETED",
    "EV_PERMISSION_CHECKED",
    "EV_PERMISSION_CONFIRMED",
    "EV_PERMISSION_DENIED",
    "EV_SCAN_COMPLETED",
    "EV_WATCH_EVENT",
    "ExecutionResult",
    "FileMatch",
    "FileOperation",
    "FileOperationKind",
    "FileWatcher",
    "PermissionDecision",
    "PermissionDeniedError",
    "PermissionManager",
    "ScanSummary",
    "SecurityPolicy",
    "WatcherEvent",
    "WORKFLOW_COMMAND",
    "WORKFLOW_FILE_OPS",
    "WORKFLOW_SCAN",
    "WorkspaceFileManager",
    "WorkspaceProfile",
    "WorkspaceScanner",
    "build_command_workflow",
    "build_file_ops_workflow",
    "build_scan_workflow",
    "emit_automation_event",
    "register_automation_system",
    "register_automation_workflows",
    "unregister_automation_system",
]
