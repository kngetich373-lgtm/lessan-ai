"""Solution Architect Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Solution Architect Agent for Lessan AI.\n"
        "Scoped feature: {feature_spec}\n"
        "Existing system constraints: {system_constraints}\n"
        "Propose a system-level design (components, data flow, "
        "integration points). Do not write code."
    ),
    variables=("feature_spec", "system_constraints"),
)


class SolutionArchitectAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="SolutionArchitectAgent",
            role="Solution Architect",
            responsibilities=[
                "Translate scoped features into system-level designs",
                "Choose integration points with the existing Lessan AI stack",
                "Identify cross-cutting concerns (performance, security, portability)",
                "Keep designs OS-agnostic per project requirements",
            ],
            objectives=[
                "Every design is implementable without redesigning existing UI/chat",
                "Designs stay consistent with SOLID principles",
            ],
            capabilities=[
                AgentCapability("propose_design", "Produce a component-level system design"),
                AgentCapability("identify_integration_points", "Map a feature onto the existing architecture"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
