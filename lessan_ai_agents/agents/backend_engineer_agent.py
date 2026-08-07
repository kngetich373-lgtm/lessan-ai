"""Backend Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Backend Engineer Agent for Lessan AI.\n"
        "Design to implement: {design}\n"
        "Existing modules affected: {affected_modules}\n"
        "Outline the server-side / core-engine implementation "
        "approach, respecting existing tool-calling architecture."
    ),
    variables=("design", "affected_modules"),
)


class BackendEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="BackendEngineerAgent",
            role="Backend Engineer",
            responsibilities=[
                "Plan core-engine and server-side implementation of approved designs",
                "Respect existing tool-calling and action-module architecture",
                "Coordinate with Database and DevOps agents on shared concerns",
            ],
            objectives=[
                "Implementation plans reuse existing modules where possible",
                "New modules stay independently testable",
            ],
            capabilities=[
                AgentCapability("plan_backend_implementation", "Outline how a design maps to backend/core-engine code"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
