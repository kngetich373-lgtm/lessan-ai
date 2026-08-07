from typing import Dict, Type
from core.workflow.models import Workflow

class WorkflowRegistry:
    """Registry for managing and retrieving workflows."""

    def __init__(self) -> None:
        self._workflows: Dict[str, Type[Workflow]] = {}

    def register(self, name: str, workflow_cls: Type[Workflow]) -> None:
        """Register a workflow class with a unique name."""
        if name in self._workflows:
            raise ValueError(f"Workflow with name '{name}' is already registered.")
        self._workflows[name] = workflow_cls

    def get(self, name: str) -> Type[Workflow]:
        """Retrieve a registered workflow class by name."""
        if name not in self._workflows:
            raise KeyError(f"Workflow with name '{name}' is not registered.")
        return self._workflows[name]

    def list_workflows(self) -> Dict[str, Type[Workflow]]:
        """List all registered workflows."""
        return self._workflows.copy()