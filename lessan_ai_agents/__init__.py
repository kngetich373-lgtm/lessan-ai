"""
Lessan AI — AI Agent Framework
===============================

Reusable, SOLID-compliant scaffolding for a multi-agent orchestration
layer sitting alongside Lessan AI's existing voice/UI/chat stack.

The core framework is ARCHITECTURE ONLY by design:
    - The eleven role agents declare responsibilities, objectives,
      capabilities, prompt templates, and memory/bus hookups, but their
      ``_run`` stays a stub unless an ``executor`` (``prompt -> str``)
      is injected (see ``lessan_ai_agents.execution.llm_backend``).
    - No workflow orchestration or software-generation logic lives in
      the core interfaces.
    - No modification of the existing UI, chat, or product surfaces.

The package also ships the application-layer consumer the core was
designed for:
    - ``orchestrator.build_project`` drives real project builds through
      all eleven agents via AgentRegistry / AgentManager / TaskQueue /
      CommunicationBus / AgentMemory, keeping the ``dev_agent`` tool
      interface (``description`` / ``language`` / ``project_name`` /
      ``timeout`` / ``speak`` / ``player``).
    - ``execution.llm_backend`` provides the default injectable LLM
      executor (Gemini with OmniRoute fallback) and the prompt-output
      parsing helpers (``strip_fences`` / ``parse_json_response``).

Consumers import the public interfaces below and wire them together at
the application layer — or simply call ``build_project``.
"""

from .core.agent_status import AgentStatus
from .core.base_agent import (
    BaseAgent,
    IAgentExecutable,
    AgentCapability,
    AgentContext,
    AgentResult,
    PromptTemplate,
)
from .core.memory import IAgentMemory, InMemoryAgentMemory, MemoryRecord
from .core.communication import (
    IAgentCommunicationBus,
    InProcessCommunicationBus,
    AgentMessage,
    MessageType,
)
from .core.task_queue import ITaskQueue, InMemoryTaskQueue, Task, TaskPriority, TaskState
from .core.agent_registry import IAgentRegistry, AgentRegistry
from .core.agent_manager import AgentManager
from .orchestrator import build_project

__all__ = [
    "AgentStatus",
    "BaseAgent",
    "IAgentExecutable",
    "AgentCapability",
    "AgentContext",
    "AgentResult",
    "PromptTemplate",
    "IAgentMemory",
    "InMemoryAgentMemory",
    "MemoryRecord",
    "IAgentCommunicationBus",
    "InProcessCommunicationBus",
    "AgentMessage",
    "MessageType",
    "ITaskQueue",
    "InMemoryTaskQueue",
    "Task",
    "TaskPriority",
    "TaskState",
    "IAgentRegistry",
    "AgentRegistry",
    "AgentManager",
    "build_project",
]

__version__ = "0.1.0"
