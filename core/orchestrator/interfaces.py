"""Interfaces for the SystemOrchestrator. All dependencies are injected
via these ABCs so the orchestrator never touches concrete subsystems."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ModelRouter(ABC):
    """Interface for routing AI model requests (implemented elsewhere)."""

    @abstractmethod
    def complete(self, prompt: str, *, system: Optional[str] = None,
                 max_tokens: int = 512, temperature: float = 0.7,
                 model: Optional[str] = None) -> str:
        """Request a text completion from an appropriate model."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if at least one model route is available."""


class WorkspaceSelector(ABC):
    @abstractmethod
    def select(self, request: "UserRequest") -> str:
        """Return the name of the workspace for ``request``."""

    @abstractmethod
    def available_workspaces(self) -> List[str]:
        """Return names of currently registered workspaces."""


class WorkflowSelector(ABC):
    @abstractmethod
    def select(self, request: "UserRequest", workspace: str) -> Optional[str]:
        """Return the name of the workflow for the request, or None."""

    @abstractmethod
    def available_workflows(self) -> List[str]:
        """Return names of workflows registered with the engine."""


class AgentSelector(ABC):
    @abstractmethod
    def select(self, request: "UserRequest", workspace: str) -> Optional[str]:
        """Return the name of the agent for the request, or None."""

    @abstractmethod
    def available_agents(self) -> List[str]:
        """Return names of currently registered agents."""


class MemoryStore(ABC):
    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Load the full long-term memory dictionary."""

    @abstractmethod
    def save(self, memory_update: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a factual update into long-term memory."""

    @abstractmethod
    def format_for_prompt(self, memory: Optional[Dict[str, Any]] = None) -> str:
        """Render a memory block suitable for prompt injection."""


class UIStateNotifier(ABC):
    @abstractmethod
    def notify(self, state_name: str, payload: Dict[str, Any]) -> None:
        """Push a state change notification to the UI layer."""