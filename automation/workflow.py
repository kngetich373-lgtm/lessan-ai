"""Workflow Engine integration for the File & Command Control System.

Registers three reusable workflows with the shared :class:`WorkflowEngine`:

* ``automation_scan`` — scan a workspace root and report a summary;
* ``automation_file_ops`` — run a parameterised batch of file operations;
* ``automation_command`` — execute one command safely.

Workflow steps carry their parameters as step data; the host application maps
the step ``action`` names to :class:`WorkspaceFileManager` /
:class:`CommandExecutor` calls (see ``automation/action.py`` for the reference
tool mapping and ``automation/agent.py`` for the agent capabilities).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.logging import get_logger
from core.workflow.models import Workflow, WorkflowStep

logger = get_logger("automation.workflow")

WORKFLOW_SCAN = "automation_scan"
WORKFLOW_FILE_OPS = "automation_file_ops"
WORKFLOW_COMMAND = "automation_command"

#: Action names used by the workflow steps (host-dispatched).
ACTION_SCAN = "automation.scan"
ACTION_LIST_DIRECTORY = "automation.list_directory"
ACTION_CREATE_FILE = "automation.create_file"
ACTION_READ_FILE = "automation.read_file"
ACTION_WRITE_FILE = "automation.write_file"
ACTION_EDIT_FILE = "automation.edit_file"
ACTION_SEARCH = "automation.search"
ACTION_RUN_COMMAND = "automation.run_command"

ALL_AUTOMATION_ACTIONS = (
    ACTION_SCAN,
    ACTION_LIST_DIRECTORY,
    ACTION_CREATE_FILE,
    ACTION_READ_FILE,
    ACTION_WRITE_FILE,
    ACTION_EDIT_FILE,
    ACTION_SEARCH,
    ACTION_RUN_COMMAND,
)


def build_scan_workflow(
    root: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
) -> Workflow:
    """Build a single-step ``automation_scan`` workflow."""
    params: Dict[str, Any] = {}
    if root:
        params["root"] = root
    if patterns:
        params["patterns"] = patterns
    if max_depth is not None:
        params["max_depth"] = max_depth
    steps = [
        WorkflowStep(
            name="scan",
            action=ACTION_SCAN,
            params=params,
            depends_on=[],
        )
    ]
    workflow = Workflow(name=WORKFLOW_SCAN, steps=steps)
    workflow.context.metadata["description"] = (
        "Scan a workspace root and report file/directory counts, sizes and extensions."
    )
    return workflow


def build_file_ops_workflow(operations: Optional[List[Dict[str, Any]]] = None) -> Workflow:
    """Build a ``automation_file_ops`` workflow from operation dicts.

    Each operation is a ``{"action": <file action>, ...kwargs}`` dict accepted
    by :meth:`WorkspaceFileManager.batch` (create_file, write_file, read_file,
    edit_file, rename, move, copy, delete, list, ...). Steps run in order.
    """
    ops = list(operations or ())
    steps = [
        WorkflowStep(
            name=f"op_{index}",
            action=ACTION_CREATE_FILE,  # placeholder; params carry the real action
            params={"op": op},
            depends_on=[f"op_{index - 1}"] if index > 0 else [],
        )
        for index, op in enumerate(ops)
    ]
    workflow = Workflow(name=WORKFLOW_FILE_OPS, steps=steps)
    workflow.context.metadata["description"] = (
        f"Run {len(ops)} file operation(s) inside the approved workspace."
    )
    return workflow


def build_command_workflow(
    command: Optional[str] = None,
    *,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    shell: bool = False,
) -> Workflow:
    """Build a single-step ``automation_command`` workflow."""
    params: Dict[str, Any] = {"command": command or ""}
    if cwd:
        params["cwd"] = cwd
    if timeout is not None:
        params["timeout"] = timeout
    if shell:
        params["shell"] = True
    steps = [
        WorkflowStep(
            name="run",
            action=ACTION_RUN_COMMAND,
            params=params,
            depends_on=[],
        )
    ]
    workflow = Workflow(name=WORKFLOW_COMMAND, steps=steps)
    workflow.context.metadata["description"] = (
        "Execute a single command inside the approved workspace with security checks."
    )
    return workflow


class AutomationScanWorkflow(Workflow):
    """Scan workflow class compatible with the WorkflowEngine registry."""

    def __init__(self) -> None:
        super().__init__(name=WORKFLOW_SCAN, steps=[])
        self.steps = build_scan_workflow().steps


class AutomationFileOpsWorkflow(Workflow):
    """Batch file-operations workflow class (host supplies the operations)."""

    def __init__(self) -> None:
        super().__init__(name=WORKFLOW_FILE_OPS, steps=[])
        self.steps = build_file_ops_workflow().steps


class AutomationCommandWorkflow(Workflow):
    """Command workflow class compatible with the WorkflowEngine registry."""

    def __init__(self) -> None:
        super().__init__(name=WORKFLOW_COMMAND, steps=[])
        self.steps = build_command_workflow().steps


def register_automation_workflows(engine=None):
    """Register the automation workflows with a WorkflowEngine.

    Args:
        engine: A :class:`core.workflow.engine.WorkflowEngine`. When None, the
            engine is resolved from the DI container (creating one if needed).
    """
    from core.di.container import container
    from core.workflow.engine import WorkflowEngine

    if engine is None:
        try:
            engine = container.try_resolve(WorkflowEngine)
        except Exception:  # noqa: BLE001
            engine = None
    if engine is None:
        engine = WorkflowEngine()
        try:
            container.register_instance(WorkflowEngine, engine)
        except Exception:  # noqa: BLE001
            pass

    for name, cls in (
        (WORKFLOW_SCAN, AutomationScanWorkflow),
        (WORKFLOW_FILE_OPS, AutomationFileOpsWorkflow),
        (WORKFLOW_COMMAND, AutomationCommandWorkflow),
    ):
        try:
            engine.registry.register(name, cls)
        except Exception as exc:  # noqa: BLE001 - already registered or host-specific
            logger.warning(f"Could not register workflow {name}: {exc}")
    return engine

