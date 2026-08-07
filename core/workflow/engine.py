from typing import Type
from core.workflow.models import Workflow
from core.workflow.executor import WorkflowExecutor
from core.workflow.registry import WorkflowRegistry
from core.workflow.history import WorkflowHistory

class WorkflowEngine:
    """Orchestrates workflow registration, execution, and history tracking."""

    def __init__(self) -> None:
        self.registry = WorkflowRegistry()
        self.executor = WorkflowExecutor()
        self.history = WorkflowHistory()

    def register_workflow(self, name: str, workflow_cls: Type[Workflow]) -> None:
        """Register a new workflow."""
        self.registry.register(name, workflow_cls)

    def run_workflow(self, name: str) -> Workflow:
        """Instantiate and execute a registered workflow."""
        workflow_cls = self.registry.get(name)
        workflow = workflow_cls()
        workflow.name = name
        
        self.history.record_start(workflow)
        try:
            self.executor.execute(workflow)
            self.history.record_completion(workflow)
        except Exception as e:
            self.history.record_error(workflow, str(e))
            raise
            
        return workflow

    def get_history(self):
        """Retrieve workflow execution history."""
        return self.history.get_history()