"""DevOps Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the DevOps Engineer Agent for Lessan AI.\n"
        "Change to release: {change_description}\n"
        "Target platforms: {platforms}\n"
        "Propose build/packaging/release steps (e.g. pip requirements, "
        "signed apt repo, .deb) needed for this change."
    ),
    variables=("change_description", "platforms"),
)


class DevOpsEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="DevOpsEngineerAgent",
            role="DevOps Engineer",
            responsibilities=[
                "Plan packaging/release steps across pip, apt, and standalone installers",
                "Maintain signed apt repository integrity for the Kali Linux path",
                "Track cross-platform dependency requirements",
            ],
            objectives=[
                "Every release plan covers all three supported operating systems",
                "Signed-package trust chain is never weakened by a release change",
            ],
            capabilities=[
                AgentCapability("plan_release", "Outline build/packaging/release steps for a change"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
