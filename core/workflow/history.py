from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4
from core.workflow.models import Workflow, WorkflowStatus

@dataclass
class WorkflowHistoryEntry:
    workflow_id: UUID
    name: str
    status: WorkflowStatus
    started_at: datetime
    id: UUID = field(default_factory=uuid4)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class WorkflowHistory:
    """Tracks the history of executed workflows."""

    def __init__(self) -> None:
        self._entries: List[WorkflowHistoryEntry] = []

    def record_start(self, workflow: Workflow) -> None:
        """Record the start of a workflow execution."""
        entry = WorkflowHistoryEntry(
            workflow_id=workflow.id,
            name=workflow.name,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now()
        )
        self._entries.append(entry)

    def record_completion(self, workflow: Workflow) -> None:
        """Record the completion of a workflow execution."""
        entry = self._find_entry(workflow.id)
        if entry:
            entry.status = workflow.status
            entry.completed_at = datetime.now()

    def record_error(self, workflow: Workflow, error: str) -> None:
        """Record an error during workflow execution."""
        entry = self._find_entry(workflow.id)
        if entry:
            entry.status = WorkflowStatus.FAILED
            entry.completed_at = datetime.now()
            entry.error = error

    def get_history(self) -> List[WorkflowHistoryEntry]:
        """Retrieve the full workflow history."""
        return self._entries.copy()

    def _find_entry(self, workflow_id: UUID) -> Optional[WorkflowHistoryEntry]:
        """Find a history entry by workflow ID."""
        for entry in self._entries:
            if entry.workflow_id == workflow_id:
                return entry
        return None