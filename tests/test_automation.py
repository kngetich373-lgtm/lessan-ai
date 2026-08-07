"""Validation tests for the File & Command Control System.

Run with:  python3 -m unittest tests.test_automation -v

Covers:
 1. SecurityPolicy: workspace containment, system-path denial, protected-path
    denial, command evaluation, config integration.
 2. PermissionManager: check/confirm/pending/audit, agent escalation,
    workspace registration, allow_path.
 3. WorkspaceFileManager: full CRUD cycle (create, read, write, edit, append,
    rename, move, copy, delete with trash), list, search, replace_text,
    batch, file_info, protected-path denial, system-path denial.
 4. CommandExecutor: echo test, unknown-command confirmation, always-deny
    (rm -rf /), timeout, history.
 5. WorkspaceScanner: scan summary, find_files (name/extension/content),
    path-containment denial.
 6. FileWatcher: baseline snapshot, created/modified/deleted detection.
 7. DI: idempotent register/unregister.
 8. Workflow: build_scan_workflow, register_automation_workflows.
 9. AutomationAgent: capabilities exist after initialization.
10. Action: tool schemas, run_command/create_file/read_file happy paths.
"""

import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation.action import (
    TOOL_SCHEMAS,
    _human_bytes,
    automation_tools,
    create_file,
    create_folder,
    edit_file,
    file_info,
    list_directory,
    read_file,
    recent_commands,
    scan_workspace,
    search_files,
    write_file,
)
from automation.command_executor import (
    CommandExecutor,
    CommandHistory,
    CommandRegistry,
)
from automation.di import register_automation_system, unregister_automation_system
from automation.file_manager import WorkspaceFileManager
from automation.models import (
    CommandReview,
    DangerLevel,
    ExecutionResult,
    FileOperationKind,
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
    ACTION_SCAN,
    WORKFLOW_SCAN,
    AutomationScanWorkflow,
    build_scan_workflow,
    register_automation_workflows,
)


# --------------------------------------------------------------------------- #
# Shared fixture
# --------------------------------------------------------------------------- #
class AutomationBase(unittest.TestCase):
    """A real policy + permissions + file manager + executor + scanner + watcher
    wired against a throw-away workspace directory."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="lessan_automation_")
        self.root = Path(self._tmp.name)
        self.policy = SecurityPolicy(
            workspace_roots=[str(self.root)],
            system_deny_roots=["/etc", "/usr", "/bin", "/sbin", "/boot",
                               "/proc", "/sys", "/dev", "/var", "/root"],
            protected_paths=["config", "core", "main.py", ".git", ".env"],
            confirmation_ttl_seconds=120.0,
            auto_confirm=False,
        )
        self.permissions = PermissionManager(self.policy)
        self.files = WorkspaceFileManager(
            self.permissions,
            default_root=self.root,
            trash_enabled=True,
        )
        self.registry = CommandRegistry()
        self.history = CommandHistory()
        self.executor = CommandExecutor(
            self.permissions,
            history=self.history,
            command_registry=self.registry,
            default_cwd=self.root,
            default_timeout=15.0,
        )
        self.scanner = WorkspaceScanner(self.permissions)
        self.watcher = FileWatcher(self.permissions)

    def tearDown(self) -> None:
        try:
            self.watcher.stop()
        except Exception:  # noqa: BLE001
            pass
        self._tmp.cleanup()


# --------------------------------------------------------------------------- #
# 1. Security policy
# --------------------------------------------------------------------------- #
class SecurityPolicyTest(AutomationBase):
    def test_workspace_containment(self) -> None:
        inside = self.root / "sub" / "file.txt"
        outside = Path("/tmp") / "outside_file.txt"
        self.assertTrue(self.policy.contains_workspace(inside))
        self.assertFalse(self.policy.contains_workspace(outside))

    def test_system_paths_denied(self) -> None:
        self.assertTrue(self.policy.is_system_path(Path("/etc/passwd")))
        self.assertTrue(self.policy.is_system_path(Path("/usr/bin/python3")))
        self.assertFalse(self.policy.is_system_path(self.root / "notes.txt"))

    def test_protected_paths(self) -> None:
        self.assertTrue(self.policy.is_protected(self.root / "config" / "x.json"))
        self.assertTrue(self.policy.is_protected(self.root / "main.py"))
        self.assertTrue(self.policy.is_protected(self.root / "proj" / ".git" / "HEAD"))
        self.assertFalse(self.policy.is_protected(self.root / "reports" / "r.txt"))

    def test_evaluate_command_known_low(self) -> None:
        review = self.policy.evaluate_command("echo hello world")
        self.assertEqual(review.danger_level, DangerLevel.LOW)
        self.assertFalse(review.always_deny)

    def test_evaluate_command_always_deny(self) -> None:
        review = self.policy.evaluate_command("rm -rf /")
        self.assertTrue(review.always_deny)

    def test_evaluate_command_unknown_is_high(self) -> None:
        review = self.policy.evaluate_command("definitely_not_a_real_command_xyz --all")
        self.assertEqual(review.danger_level, DangerLevel.HIGH)

    def test_allow_path_expands_workspace(self) -> None:
        extra = Path("/tmp") / "allowed_extra"
        self.assertFalse(self.policy.contains_workspace(extra))
        self.policy.allow_path(extra)
        self.assertTrue(self.policy.is_allowlisted(extra))

    def test_register_command_level(self) -> None:
        self.policy.register_command_level("my_tool", DangerLevel.LOW)
        review = self.policy.evaluate_command("my_tool --flag")
        self.assertEqual(review.danger_level, DangerLevel.LOW)
        self.assertFalse(review.always_deny)

    def test_as_dict(self) -> None:
        payload = self.policy.as_dict()
        self.assertIn("workspace_roots", payload)
        self.assertIn("app_root", payload)


# --------------------------------------------------------------------------- #
# 2. Permission manager
# --------------------------------------------------------------------------- #
class PermissionManagerTest(AutomationBase):
    def test_safe_file_op_allowed(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.CREATE_FILE,
            source=self.root / "a.txt",
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_confirmation)

    def test_system_path_denied(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.WRITE_FILE,
            source=Path("/etc/hosts"),
        )
        self.assertFalse(decision.allowed)

    def test_protected_path_denied(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.DELETE_FILE,
            source=self.root / "config" / "secrets.json",
        )
        self.assertFalse(decision.allowed)

    def test_high_op_user_needs_confirmation(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.DELETE_FILE,
            source=self.root / "old.txt",
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)
        self.assertTrue(decision.token)

    def test_confirm_flow(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.DELETE_FILE,
            source=self.root / "old.txt",
        )
        self.assertTrue(self.permissions.confirm(decision.token, actor="user"))
        self.assertEqual(self.permissions.pending(), [])

    def test_confirm_wrong_token(self) -> None:
        self.assertFalse(self.permissions.confirm("bogus-token", actor="user"))

    def test_agent_medium_needs_confirmation(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.WRITE_FILE,
            source=self.root / "a.txt",
            actor="agent",
        )
        self.assertTrue(decision.requires_confirmation)

    def test_agent_high_denied_without_confirm(self) -> None:
        decision = self.permissions.check(
            FileOperationKind.DELETE_FILE,
            source=self.root / "old.txt",
            actor="agent",
        )
        self.assertTrue(decision.requires_confirmation)

    def test_audit_recorded(self) -> None:
        self.permissions.check(
            FileOperationKind.CREATE_FILE, source=self.root / "audited.txt"
        )
        records = self.permissions.audit()
        self.assertGreaterEqual(len(records), 1)

    def test_register_workspace(self) -> None:
        profile = self.permissions.register_workspace("/tmp/new_ws", name="scratch")
        self.assertIsInstance(profile, WorkspaceProfile)
        self.assertTrue(self.policy.contains_workspace(Path("/tmp/new_ws/x")))

    def test_allow_path(self) -> None:
        self.permissions.allow_path(self.root / "extra")
        self.assertTrue(self.policy.is_allowlisted(self.root / "extra"))


# --------------------------------------------------------------------------- #
# 3. File manager
# --------------------------------------------------------------------------- #
class FileManagerTest(AutomationBase):
    def test_full_crud_cycle(self) -> None:
        created_folder = self.files.create_folder("projects/demo", actor="user")
        self.assertTrue(Path(created_folder["path"]).is_dir())

        created = self.files.create_file("projects/demo/readme.md",
                                         content="hello world", actor="user")
        self.assertEqual(created["bytes"], 11)
        target = self.root / "projects" / "demo" / "readme.md"
        self.assertTrue(target.exists())

        payload = self.files.read_file("projects/demo/readme.md", actor="user")
        self.assertEqual(payload["content"], "hello world")

        self.files.write_file("projects/demo/readme.md", "v2 content", actor="user")
        self.assertEqual(target.read_text(encoding="utf-8"), "v2 content")

        edited = self.files.edit_file("projects/demo/readme.md",
                                      old_text="v2", new_text="version-2", actor="user")
        self.assertEqual(edited["replaced"], 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "version-2 content")

        self.files.append_file("projects/demo/readme.md", " more", actor="user")
        self.assertEqual(target.read_text(encoding="utf-8"), "version-2 content more")

    def test_rename_move_copy(self) -> None:
        src = self.root / "original.txt"
        src.write_text("payload", encoding="utf-8")

        renamed = self.files.rename("original.txt", "renamed.txt", actor="user")
        self.assertTrue(self.root.joinpath(renamed["path"]).exists())

        moved = self.files.move("renamed.txt", "nested/moved.txt", actor="user")
        moved_path = self.root / "nested" / "moved.txt"
        self.assertTrue(moved_path.exists())

        copied = self.files.copy("nested/moved.txt", "nested/copied.txt", actor="user")
        self.assertTrue(self.root.joinpath(copied["path"]).exists())

    def test_list_directory_and_file_info(self) -> None:
        (self.root / "alpha.txt").write_text("a", encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "beta.txt").write_text("b", encoding="utf-8")

        listing = self.files.list_directory(".", actor="user")
        self.assertEqual(listing["count"], 2)

        info = self.files.file_info("alpha.txt", actor="user")
        self.assertEqual(info["kind"], "file")
        self.assertEqual(info["size"], 1)

    def test_search_files(self) -> None:
        (self.root / "notes.md").write_text("important content here",
                                           encoding="utf-8")
        (self.root / "todo.txt").write_text("buy milk", encoding="utf-8")

        by_extension = self.files.search_files(extension="md", actor="user")
        self.assertEqual(by_extension["count"], 1)
        self.assertIn("notes.md", by_extension["matches"][0]["path"])

        by_name = self.files.search_files(name="*.txt", actor="user")
        self.assertEqual(by_name["count"], 1)

        by_content = self.files.search_files(content="important", actor="user")
        self.assertEqual(by_content["count"], 1)

    def test_replace_text(self) -> None:
        (self.root / "greet.txt").write_text("hi hi hi", encoding="utf-8")
        payload = self.files.replace_text("greet.txt", "hi", "yo",
                                          count=2, actor="user")
        self.assertEqual(payload["total_replacements"], 2)
        self.assertEqual((self.root / "greet.txt").read_text(encoding="utf-8"),
                         "yo yo hi")

    def test_delete_file_two_step_confirmation(self) -> None:
        doomed = self.root / "doomed.txt"
        doomed.write_text("x", encoding="utf-8")

        with self.assertRaises(ConfirmationRequiredError) as ctx:
            self.files.delete_file("doomed.txt", actor="user")
        token = ctx.exception.token
        self.assertTrue(token)
        self.assertTrue(self.permissions.confirm(token, actor="user"))

        result = self.files.delete_file("doomed.txt", actor="user", confirm=True)
        self.assertFalse(doomed.exists())
        self.assertIn("doomed.txt", result["path"])

    def test_delete_folder(self) -> None:
        folder = self.root / "expendable"
        folder.mkdir()
        (folder / "inside.txt").write_text("x", encoding="utf-8")
        result = self.files.delete_folder("expendable", recursive=True,
                                          actor="user", confirm=True)
        self.assertFalse(folder.exists())
        self.assertIn("expendable", result["path"])

    def test_delete_moves_to_trash(self) -> None:
        doomed = self.root / "trashed.txt"
        doomed.write_text("x", encoding="utf-8")
        self.files.delete_file("trashed.txt", actor="user", confirm=True)
        self.assertFalse(doomed.exists())
        trash_root = self.root / ".trash"
        self.assertTrue(trash_root.exists())

    def test_batch_operations(self) -> None:
        payload = self.files.batch(
            [
                {"action": "create_folder", "path": "batchdir"},
                {"action": "create_file", "path": "batchdir/one.txt",
                 "content": "one"},
                {"action": "read_file", "path": "batchdir/one.txt"},
                {"action": "write_file", "path": "batchdir/two.txt",
                 "content": "two"},
                {"action": "delete", "path": "batchdir/two.txt"},
            ],
            actor="user",
            confirm=True,
        )
        self.assertEqual(payload["succeeded"], 5)
        self.assertEqual(payload["failed"], 0)

    def test_write_outside_workspace_denied(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.files.write_file("/tmp/outside.txt", "x", actor="user")

    def test_write_system_path_denied(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.files.write_file("/etc/evil.txt", "x", actor="user")

    def test_delete_protected_denied(self) -> None:
        protected = self.root / "config"
        protected.mkdir(exist_ok=True)
        with self.assertRaises(PermissionDeniedError):
            self.files.delete_folder("config", recursive=True, actor="user",
                                     confirm=True)
        self.assertTrue(protected.exists())

    def test_agent_write_requires_confirmation(self) -> None:
        with self.assertRaises(ConfirmationRequiredError):
            self.files.write_file("agent.txt", "x", actor="agent")


# --------------------------------------------------------------------------- #
# 4. Command executor
# --------------------------------------------------------------------------- #
class CommandExecutorTest(AutomationBase):
    def test_run_known_low_command(self) -> None:
        result = self.executor.run("echo hello from lessan", actor="user")
        self.assertTrue(result.success)
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello from lessan", result.stdout)

    def test_run_unknown_command_requires_confirmation(self) -> None:
        with self.assertRaises(ConfirmationRequiredError) as ctx:
            self.executor.run("totally_bogus_command_abc", actor="user")
        self.assertTrue(ctx.exception.token)

    def test_always_denied_command(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.executor.run("rm -rf /", actor="user", confirm=True)

    def test_timeout(self) -> None:
        self.policy.register_command_level("python", DangerLevel.LOW)
        result = self.executor.run(
            "python -c \"import time; time.sleep(2)\"",
            timeout=0.3,
            actor="user",
        )
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)

    def test_history_recorded(self) -> None:
        self.executor.run("echo history-test", actor="user")
        records = self.executor.history.recent(limit=5)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]["command"], "echo history-test")

    def test_registry_known_commands(self) -> None:
        names = self.registry.known_names
        self.assertIn("echo", names)
        self.assertIn("ls", names)

    def test_run_async(self) -> None:
        thread, holder = self.executor.run_async("echo async-run", actor="user")
        thread.join(timeout=5.0)
        self.assertTrue(holder.result.success)


# --------------------------------------------------------------------------- #
# 5. Workspace scanner
# --------------------------------------------------------------------------- #
class WorkspaceScannerTest(AutomationBase):
    def test_scan_summary(self) -> None:
        (self.root / "a.py").write_text("print(1)", encoding="utf-8")
        (self.root / "b.md").write_text("hello", encoding="utf-8")
        (self.root / "notes").mkdir()
        (self.root / "notes" / "deep.txt").write_text("x", encoding="utf-8")

        summary = self.scanner.scan(self.root, actor="user")
        self.assertIsInstance(summary, ScanSummary)
        self.assertEqual(summary.file_count, 3)
        self.assertEqual(summary.dir_count, 1)
        self.assertGreaterEqual(summary.total_bytes, 3)
        self.assertEqual(summary.extensions.get(".py"), 1)
        self.assertEqual(summary.extensions.get(".md"), 1)

    def test_scan_patterns(self) -> None:
        (self.root / "a.py").write_text("x", encoding="utf-8")
        (self.root / "b.txt").write_text("x", encoding="utf-8")
        summary = self.scanner.scan(self.root, patterns=["*.py"], actor="user")
        self.assertEqual(summary.file_count, 1)

    def test_scan_ignores_default_junk(self) -> None:
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "lib.py").write_text("x", encoding="utf-8")
        (self.root / "__pycache__").mkdir()
        (self.root / "__pycache__" / "m.pyc").write_bytes(b"\x00")
        (self.root / "real.py").write_text("x", encoding="utf-8")
        summary = self.scanner.scan(self.root, actor="user")
        self.assertEqual(summary.file_count, 1)

    def test_scan_limit_truncates(self) -> None:
        for index in range(5):
            (self.root / f"f{index}.txt").write_text("x", encoding="utf-8")
        summary = self.scanner.scan(self.root, limit=2, actor="user")
        self.assertTrue(summary.truncated)
        self.assertEqual(summary.file_count, 2)

    def test_find_files(self) -> None:
        (self.root / "report_final.pdf").write_bytes(b"%PDF-1.4")
        (self.root / "report.txt").write_text("quarterly numbers: 42", encoding="utf-8")

        by_name = self.scanner.find_files(root=self.root, query="report")
        self.assertEqual(by_name["count"], 2)

        by_extension = self.scanner.find_files(root=self.root, extension="pdf")
        self.assertEqual(by_extension["count"], 1)

        by_content = self.scanner.find_files(root=self.root, content="42",
                                             snippet=True)
        self.assertEqual(by_content["count"], 1)
        self.assertTrue(by_content["matches"][0]["snippet"])

    def test_scan_outside_workspace_denied(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.scanner.scan("/etc", actor="user")


# --------------------------------------------------------------------------- #
# 6. File watcher
# --------------------------------------------------------------------------- #
class FileWatcherTest(AutomationBase):
    def test_snapshot_diff(self) -> None:
        # Don't start the background thread; exercise snapshot() directly
        # to avoid timing races with the test assertions.
        self.watcher._snapshots[self.root] = self.watcher._build_snapshot(self.root)

        (self.root / "created.txt").write_text("c", encoding="utf-8")
        events = self.watcher.snapshot()
        self.assertEqual([e["event_type"] for e in events], ["created"])
        self.assertIn("created.txt", events[0]["path"])

        time.sleep(0.1)
        (self.root / "created.txt").write_text("modified", encoding="utf-8")
        events = self.watcher.snapshot()
        self.assertEqual([e["event_type"] for e in events], ["modified"])

        (self.root / "created.txt").unlink()
        events = self.watcher.snapshot()
        self.assertEqual([e["event_type"] for e in events], ["deleted"])

        self.assertGreaterEqual(len(self.watcher.recent(limit=10)), 3)

    def test_watcher_patterns(self) -> None:
        # Same approach: no background thread.
        self.watcher._patterns = {"*.md"}
        self.watcher._snapshots[self.root] = self.watcher._build_snapshot(self.root)
        (self.root / "a.md").write_text("x", encoding="utf-8")
        (self.root / "b.txt").write_text("x", encoding="utf-8")
        events = self.watcher.snapshot()
        self.assertEqual(len(events), 1)
        self.assertIn("a.md", events[0]["path"])


# --------------------------------------------------------------------------- #
# 7. DI container
# --------------------------------------------------------------------------- #
class DiIntegrationTest(unittest.TestCase):
    def test_register_unregister(self) -> None:
        from core.di.container import Container

        from automation.command_executor import (
            CommandExecutor,
            CommandHistory,
            CommandRegistry,
        )
        from automation.file_manager import WorkspaceFileManager
        from automation.permissions import PermissionManager
        from automation.scanner import WorkspaceScanner
        from automation.security import SecurityPolicy
        from automation.watcher import FileWatcher

        container = Container()
        register_automation_system(container)
        register_automation_system(container)  # idempotent

        self.assertIsInstance(container.resolve(SecurityPolicy), SecurityPolicy)
        self.assertIsInstance(container.resolve(PermissionManager), PermissionManager)
        self.assertIsInstance(container.resolve(WorkspaceFileManager), WorkspaceFileManager)
        self.assertIsInstance(container.resolve(CommandExecutor), CommandExecutor)
        self.assertIsInstance(container.resolve(CommandHistory), CommandHistory)
        self.assertIsInstance(container.resolve(CommandRegistry), CommandRegistry)
        self.assertIsInstance(container.resolve(WorkspaceScanner), WorkspaceScanner)
        self.assertIsInstance(container.resolve(FileWatcher), FileWatcher)

        permissions = container.resolve(PermissionManager)
        executor = container.resolve(CommandExecutor)
        self.assertIs(executor.permissions, permissions)
        self.assertIs(permissions.policy.command_registry,
                      container.resolve(CommandRegistry))

        unregister_automation_system(container)
        self.assertFalse(container.has(WorkspaceFileManager))


# --------------------------------------------------------------------------- #
# 8. Workflow engine
# --------------------------------------------------------------------------- #
class WorkflowIntegrationTest(unittest.TestCase):
    def test_build_scan_workflow(self) -> None:
        workflow = build_scan_workflow("~/Desktop", patterns=["*.py"])
        self.assertEqual(workflow.name, WORKFLOW_SCAN)
        self.assertEqual(len(workflow.steps), 1)
        self.assertEqual(workflow.steps[0].action, ACTION_SCAN)
        self.assertEqual(workflow.steps[0].params["root"], "~/Desktop")

    def test_register_workflows(self) -> None:
        from core.workflow.engine import WorkflowEngine

        engine = WorkflowEngine()
        register_automation_workflows(engine)
        cls = engine.registry.get(WORKFLOW_SCAN)
        created = cls()
        self.assertIsInstance(created, AutomationScanWorkflow)


# --------------------------------------------------------------------------- #
# 9. AutomationAgent
# --------------------------------------------------------------------------- #
class AutomationAgentTest(unittest.TestCase):
    def test_agent_capabilities(self) -> None:
        from automation.agent import AutomationAgent

        agent = AutomationAgent()
        agent.initialize({})
        for capability in ("run_command", "create_file", "read_file",
                           "write_file", "edit_file", "delete_file",
                           "search_files", "scan_workspace", "file_info",
                           "list_directory"):
            self.assertTrue(agent.has_capability(capability),
                            f"missing capability: {capability}")

    def test_agent_registry_registered(self) -> None:
        from automation.agent import AutomationAgent

        from agents.framework.agent_registry import agent_registry

        self.assertIn(AutomationAgent.name, agent_registry.available())


# --------------------------------------------------------------------------- #
# 10. Tool actions
# --------------------------------------------------------------------------- #
class ActionToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="lessan_action_")
        self.root = Path(self._tmp.name)
        # Make the shared/global policy accept this test's workspace.
        from core.di.container import container

        from automation.di import register_automation_system
        from automation.permissions import PermissionManager

        register_automation_system(container)
        container.resolve(PermissionManager).register_workspace(
            self.root, name="action-test"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_tool_schemas_present(self) -> None:
        self.assertIn("run_command", TOOL_SCHEMAS)
        self.assertIn("create_file", TOOL_SCHEMAS)
        self.assertIn("delete_file", TOOL_SCHEMAS)

    def test_automation_tools_list(self) -> None:
        tools = automation_tools()
        names = {tool.name for tool in tools}
        self.assertIn("run_command", names)
        self.assertIn("scan_workspace", names)
        self.assertTrue(all(tool.description for tool in tools))

    def test_safe_tool_happy_paths(self) -> None:
        result = create_file({"path": str(self.root / "tool.txt"),
                              "content": "tool content"})
        self.assertIn("created", result.lower())

        result = read_file({"path": str(self.root / "tool.txt")})
        self.assertIn("tool content", result)

        listing = list_directory({"path": str(self.root)})
        self.assertIn("tool.txt", listing)

        report = scan_workspace({"root": str(self.root)})
        self.assertIn("Files:", report)

    def test_agent_medium_tool_requires_confirmation(self) -> None:
        # Tools run as 'agent'; MEDIUM file writes therefore need a token.
        result = write_file({"path": str(self.root / "agent.txt"),
                             "content": "x"})
        self.assertIn("token", result.lower())

        result = edit_file({"path": str(self.root / "agent.txt"),
                            "old_text": "x", "new_text": "y"})
        self.assertIn("token", result.lower())

    def test_recent_commands_and_search(self) -> None:
        (self.root / "needle.txt").write_text("unique needle text",
                                              encoding="utf-8")
        found = search_files({"content": "needle", "max_results": 10})
        self.assertIn("needle.txt", found)
        history = recent_commands({"limit": 5})
        self.assertIsInstance(history, str)

    def test_human_bytes(self) -> None:
        self.assertEqual(_human_bytes(500), "500 B")
        self.assertEqual(_human_bytes(2048), "2.0 KB")


if __name__ == "__main__":
    unittest.main()








