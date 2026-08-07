"""Frontend Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Frontend Engineer Agent for Lessan AI.\n"
        "Design to implement: {design}\n"
        "Target platforms: {platforms}\n"
        "Outline the implementation approach for the client-side "
        "layer without modifying the existing UI/chat components."
    ),
    variables=("design", "platforms"),
)


class FrontendEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="FrontendEngineerAgent",
            role="Frontend Engineer",
            responsibilities=[
                "Plan client-side implementation of approved designs",
                "Ensure cross-platform consistency (Windows/macOS/Linux)",
                "Respect the constraint of not modifying existing UI/chat",
            ],
            objectives=[
                "Implementation plans are consistent with the approved design",
                "No existing UI or chat component requires modification",
            ],
            capabilities=[
                AgentCapability("plan_frontend_implementation", "Outline how a design maps to client-side code"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
