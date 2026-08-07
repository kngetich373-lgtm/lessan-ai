from typing import List
from core.workflow.models import Workflow, WorkflowStep, WorkflowStatus

class WorkflowExecutor:
    """Executes workflows step by step, ensuring dependencies are resolved."""

    def __init__(self) -> None:
        self._active_workflows: List[Workflow] = []

    def execute(self, workflow: Workflow) -> None:
        """Start executing a workflow."""
        if workflow.status != WorkflowStatus.PENDING:
            raise ValueError("Workflow must be in PENDING state to start execution.")
        
        workflow.status = WorkflowStatus.RUNNING
        self._active_workflows.append(workflow)
        self._execute_steps(workflow)

    def _execute_steps(self, workflow: Workflow) -> None:
        """Execute all steps in the workflow."""
        completed_steps = set()
        while workflow.steps:
            for step in workflow.steps:
                if all(dep in completed_steps for dep in step.depends_on):
                    self._execute_step(workflow, step)
                    completed_steps.add(step.name)
                    workflow.steps.remove(step)
                    break
            else:
                raise RuntimeError("Circular dependency detected or unresolved dependencies.")

        workflow.status = WorkflowStatus.COMPLETED

    def _execute_step(self, workflow: Workflow, step: WorkflowStep) -> None:
        """Execute a single workflow step."""
        try:
            # Placeholder for actual step execution logic
            print(f"Executing step: {step.name} with action: {step.action}")
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            raise RuntimeError(f"Failed to execute step {step.name}: {e}")

    def cancel(self, workflow: Workflow) -> None:
        """Cancel an active workflow."""
        if workflow in self._active_workflows:
            workflow.status = WorkflowStatus.CANCELLED
            self._active_workflows.remove(workflow)