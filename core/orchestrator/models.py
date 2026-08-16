"""Request/result models used by the SystemOrchestrator."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass
class UserRequest:
    """An incoming user request received by the orchestrator."""
    source: str
    text: str
    session_id: Optional[str] = None
    workspace_hint: Optional[str] = None
    workflow_hint: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)


class OrchestrationResult:
    """Result of a request processed by the orchestrator.

    ``task_id`` is populated when the request is submitted in background
    mode. This makes the result a stable handle for both synchronous and
    scheduled execution.
    """

    def __init__(self, request: UserRequest):
        self.request = request
        self.success = False
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        self.workspace: Optional[str] = None
        self.workflow: Optional[str] = None
        self.agent: Optional[str] = None
        self.task_id: Optional[str] = None
        self.started_at = datetime.now()
        self.completed_at: Optional[datetime] = None

    @property
    def done(self) -> bool:
        """Whether processing has reached a terminal state."""
        return self.completed_at is not None

    def complete(self, output: str) -> None:
        self.output = str(output)
        self.error = None
        self.success = True
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        self.error = str(error)
        self.output = None
        self.success = False
        self.completed_at = datetime.now()
