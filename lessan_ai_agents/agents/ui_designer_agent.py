"""UI Designer Agent.

Note: per project rules ("Do not modify the UI", "Do not redesign the
project") this agent's role is advisory only — it proposes UI
considerations for *new* surfaces if/when requested, and never
touches Lessan AI's existing adaptive UI.
"""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the UI Designer Agent for Lessan AI.\n"
        "Design brief: {design_brief}\n"
        "Existing UI constraints: {ui_constraints}\n"
        "Propose layout/interaction considerations without altering "
        "the existing adaptive UI or chat surface."
    ),
    variables=("design_brief", "ui_constraints"),
)


class UIDesignerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="UIDesignerAgent",
            role="UI Designer",
            responsibilities=[
                "Propose interaction and layout considerations for new surfaces",
                "Preserve consistency with the existing adaptive/transparent UI",
                "Flag any request that would require modifying existing UI or chat",
            ],
            objectives=[
                "New UI proposals never require touching existing UI or chat code",
                "Designs remain consistent across Windows/macOS/Linux",
            ],
            capabilities=[
                AgentCapability("propose_layout", "Suggest layout/interaction patterns for a new surface"),
                AgentCapability("flag_ui_conflict", "Detect when a request would require UI/chat modification"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
