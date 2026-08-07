"""Documentation Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Documentation Engineer Agent for Lessan AI.\n"
        "Change to document: {change_description}\n"
        "Audience: {audience}\n"
        "Propose what README/INSTALL/guide sections need updating, "
        "and draft an outline. Do not rewrite the whole document."
    ),
    variables=("change_description", "audience"),
)


class DocumentationEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="DocumentationEngineerAgent",
            role="Documentation Engineer",
            responsibilities=[
                "Keep README.md and INSTALL_KALI.md accurate as the project evolves",
                "Outline documentation updates required by a given change",
                "Preserve existing documentation structure and tone",
            ],
            objectives=[
                "No shipped feature goes undocumented",
                "Documentation changes stay minimal and targeted",
            ],
            capabilities=[
                AgentCapability("outline_doc_update", "Propose which docs/sections need updating for a change"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
