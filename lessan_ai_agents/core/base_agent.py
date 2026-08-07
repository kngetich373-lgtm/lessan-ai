"""
BaseAgent and the core interfaces every agent implements.

Design notes (SOLID):
- Single Responsibility: BaseAgent only holds identity, capability
  metadata, and lifecycle/status bookkeeping. It does NOT queue tasks,
  route messages, or persist memory — those are separate collaborators
  injected in, not owned.
- Open/Closed: concrete agents (CEO, QA, etc.) extend BaseAgent and
  override `describe()` / `build_prompt()`; the base class never needs
  to change to support a new role.
- Liskov Substitution: any BaseAgent subclass can stand in wherever
  IAgentExecutable is expected.
- Interface Segregation: IAgentExecutable (execution contract) is
  separate from IAgentMemory (storage contract) and
  IAgentCommunicationBus (messaging contract) — an agent depends only
  on the interfaces it actually uses.
- Dependency Inversion: BaseAgent depends on the IAgentMemory and
  IAgentCommunicationBus *abstractions*, injected via the constructor,
  never on concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from .agent_status import AgentStatus, is_valid_transition


@dataclass(frozen=True)
class AgentCapability:
    """A single named capability an agent claims to provide.

    e.g. AgentCapability(name="code_review", description="Reviews pull
    requests for style and correctness issues")
    """

    name: str
    description: str = ""


@dataclass(frozen=True)
class PromptTemplate:
    """A reusable prompt template for an agent's role.

    `variables` documents the placeholders `template` expects, so
    callers can validate a context dict before formatting. This class
    holds no execution logic on purpose — formatting is a pure
    function (`render`) with no side effects or I/O.
    """

    template: str
    variables: tuple = field(default_factory=tuple)

    def render(self, **kwargs: Any) -> str:
        missing = [v for v in self.variables if v not in kwargs]
        if missing:
            raise ValueError(f"Missing template variables: {missing}")
        return self.template.format(**kwargs)


@dataclass
class AgentContext:
    """Input handed to an agent for a single unit of work.

    Deliberately generic (task payload + free-form metadata) so the
    framework stays agent-agnostic; concrete agents interpret
    `payload` according to their own contract.
    """

    task_id: str
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentResult:
    """Output of a single agent execution."""

    task_id: str
    agent_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class IAgentExecutable(Protocol):
    """Execution contract — the only thing a task orchestrator needs
    to know about an agent to run it. Kept separate from BaseAgent so
    lightweight/mock agents can satisfy it without inheritance.
    """

    name: str

    def execute(self, context: AgentContext) -> AgentResult: ...


class BaseAgent(ABC):
    """Abstract base for every role-specific agent in the framework.

    Subclasses MUST implement:
        - `describe()`      -> static role metadata
        - `build_prompt()`  -> role-specific prompt from a context

    Subclasses MAY override:
        - `execute()`       -> default impl just builds a prompt and
                                delegates to `_run(prompt, context)`,
                                which subclasses implement instead if
                                they don't need to change the envelope.
    """

    def __init__(
        self,
        name: str,
        role: str,
        responsibilities: list[str],
        objectives: list[str],
        capabilities: list[AgentCapability],
        prompt_template: PromptTemplate,
        memory: "Optional[IAgentMemory]" = None,
        communication_bus: "Optional[IAgentCommunicationBus]" = None,
    ) -> None:
        self.name = name
        self.role = role
        self.responsibilities = list(responsibilities)
        self.objectives = list(objectives)
        self.capabilities = list(capabilities)
        self.prompt_template = prompt_template
        self.memory = memory
        self.communication_bus = communication_bus
        self._status = AgentStatus.UNINITIALIZED

    # -- status lifecycle -------------------------------------------------

    @property
    def status(self) -> AgentStatus:
        return self._status

    def set_status(self, target: AgentStatus) -> None:
        """Transition the agent's status, enforcing the legal-transition
        table so illegal jumps (e.g. IDLE -> COMPLETED) fail loudly."""
        if not is_valid_transition(self._status, target):
            raise ValueError(
                f"Illegal status transition for agent '{self.name}': "
                f"{self._status.value} -> {target.value}"
            )
        self._status = target

    def initialize(self) -> None:
        """Move the agent from UNINITIALIZED to IDLE. Idempotent no-op
        if already past that point."""
        if self._status == AgentStatus.UNINITIALIZED:
            self.set_status(AgentStatus.IDLE)

    # -- role metadata ------------------------------------------------------

    @abstractmethod
    def describe(self) -> dict:
        """Return static role metadata: responsibilities, objectives,
        capabilities. Used by AgentRegistry for discovery/introspection
        without needing to execute the agent."""
        raise NotImplementedError

    # -- prompt building ------------------------------------------------

    @abstractmethod
    def build_prompt(self, context: AgentContext) -> str:
        """Render this agent's PromptTemplate against a given context."""
        raise NotImplementedError

    # -- execution --------------------------------------------------------

    def execute(self, context: AgentContext) -> AgentResult:
        """Default execution envelope: status bookkeeping + delegation
        to `_run`. Subclasses override `_run`, not `execute`, unless
        they need a genuinely different lifecycle."""
        self.set_status(AgentStatus.ASSIGNED)
        self.set_status(AgentStatus.RUNNING)
        try:
            output = self._run(context)
            self.set_status(AgentStatus.COMPLETED)
            self.set_status(AgentStatus.IDLE)
            return AgentResult(
                task_id=context.task_id,
                agent_name=self.name,
                success=True,
                output=output,
            )
        except Exception as exc:  # noqa: BLE001 - deliberately broad at the boundary
            self.set_status(AgentStatus.FAILED)
            self.set_status(AgentStatus.IDLE)
            return AgentResult(
                task_id=context.task_id,
                agent_name=self.name,
                success=False,
                error=str(exc),
            )

    @abstractmethod
    def _run(self, context: AgentContext) -> Any:
        """Role-specific unit of work. NOTE: per project scope, concrete
        agents in this framework implement this as a description of
        *what they would do*, not as software-generation logic. See
        each agent module's docstring."""
        raise NotImplementedError


# Deferred imports for type hints only (avoids circular imports at
# module load time, since memory.py / communication.py don't depend
# on base_agent.py).
from .memory import IAgentMemory  # noqa: E402
from .communication import IAgentCommunicationBus  # noqa: E402
