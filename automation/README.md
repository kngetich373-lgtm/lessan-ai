# File & Command Control System (`automation/`)

Safe file operations, secure command execution, permission enforcement,
workspace scanning/searching and filesystem watching — all constrained by a
central `SecurityPolicy` that blocks system-critical paths, enforces workspace
containment and requires expiring confirmation tokens for destructive operations.

## Quick start

```python
from automation import (
    SecurityPolicy,
    PermissionManager,
    WorkspaceFileManager,
    CommandExecutor,
    WorkspaceScanner,
)

policy   = SecurityPolicy(workspace_roots=["~/Documents"])
perms    = PermissionManager(policy)
files    = WorkspaceFileManager(perms, default_root="~/Documents")
executor = CommandExecutor(perms, default_cwd="~/Documents")
scanner  = WorkspaceScanner(perms)

files.create_file("notes.txt", content="hello world")
result = executor.run("echo hello")
summary = scanner.scan()
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Host / main.py / agent / workspace dispatcher          │
│    action.py  (TOOL_SCHEMAS, tool entry points)         │
│    agent.py   (@agent_registry.register)                │
└────────────────────────┬─────────────────────────────────┘
                         │ resolves via DI container
┌────────────────────────▼─────────────────────────────────┐
│  WorkspaceFileManager    CommandExecutor   WorkspaceScanner │
│  FileWatcher             (uses PermissionManager)         │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  PermissionManager  → SecurityPolicy                     │
│    check / confirm / revoke / pending / audit            │
│    workspace containment · system-deny · protected paths  │
│    danger-level escalation · confirmation tokens         │
└──────────────────────────────────────────────────────────┘
```

## Security model

| Layer | What it blocks |
|-------|---------------|
| **Workspace containment** | Every source / destination must be under an approved workspace root |
| **System-critical roots** | `/etc`, `/usr`, `/bin`, `~/.ssh`, … always denied |
| **Protected paths** | `.git`, `main.py`, `config`, `core`, `automation`, … — never deleted/moved/overwritten |
| **Command signatures** | Always-deny (`rm -rf /`, `mkfs`, `curl|sh`); dangerous (`sudo`, `apt`, `rm -rf *`) |
| **Danger escalation** | HIGH/CRITICAL user ops require an expiring confirmation token; agent ops of MEDIUM+ also require one |

## Files

| Module | Purpose |
|--------|---------|
| `models.py` | Value objects: `DangerLevel`, `FileOperationKind`, `ExecutionResult`, `FileOperation`, `CommandReview`, `PermissionDecision`, `WorkspaceProfile`, `FileMatch`, `CommandSpec`, `ScanSummary`, `WatcherEvent` |
| `security.py` | `SecurityPolicy` — workspace roots, system-deny roots, protected paths, always-deny / dangerous command regex tables, `evaluate_command()` |
| `permissions.py` | `PermissionManager` — `check()`, `confirm()`, `revoke()`, `pending()`, `audit()`, `register_workspace()`, `allow_path()` |
| `file_manager.py` | `WorkspaceFileManager` — create, read, write, edit, append, rename, move, copy, delete (soft-delete to `.trash`), list, search, replace, batch, file_info, open |
| `command_executor.py` | `CommandRegistry`, `CommandHistory`, `CommandExecutor` — runs commands as child processes with timeout, output cap, permission enforcement |
| `scanner.py` | `WorkspaceScanner` — `scan()` (summary) and `find_files()` (search by name / extension / content / glob) |
| `watcher.py` | `FileWatcher` — polling-based filesystem watcher with snapshot diffing and event buffering |
| `interfaces.py` | Protocol contracts (`IFileManager`, `ICommandExecutor`, etc.) and `AutomationTool` metadata for host dispatchers |
| `workflow.py` | Workflow Engine integration: `build_scan_workflow()`, `build_file_ops_workflow()`, `build_command_workflow()` |
| `action.py` | Host-dispatched tool entry points and `TOOL_SCHEMAS` JSON schema dicts |
| `agent.py` | `AutomationAgent` — 15 capabilities (list, create, read, write, edit, delete, search, scan, run, confirm, …) |
| `di.py` | `register_automation_system()` / `unregister_automation_system()` — idempotent DI registration |
| `events.py` | Event topics (`EV_FILE_CREATED`, `EV_COMMAND_COMPLETED`, …) and failure-tolerant `emit_automation_event()` |
| `__init__.py` | Public API re-exports |

## Configuration

All settings live under the `automation` section of `core/configuration/config.py`
(or `config/lessan_config.json`) and are read by `SecurityPolicy` and `automation.di`
through safe defaults.

```jsonc
"automation": {
    "workspace_roots":         ["~/Desktop", "~/Documents", "~/Downloads", "~/Lessan"],
    "app_root":                null,           // null → BASE_DIR
    "system_deny_roots":       ["/etc", …],
    "protected_paths":         [".git", "config", "core", "main.py", …],
    "confirmation_ttl_seconds": 120.0,
    "auto_confirm":            false,
    "trash_enabled":           true,
    "max_file_read_chars":     100000,
    "max_output_chars":        100000,
    "command_timeout_seconds": 60.0,
    "max_history":             200,
    "watch_enabled":           false,
    "watch_interval_seconds":  2.0
}
```

Override via env vars: `LESSAN__AUTOMATION__AUTO_CONFIRM=true`.

## Tests

```bash
python -m unittest tests.test_automation -v   # 59 tests
python -m unittest discover -s tests          # all 116 tests
```
