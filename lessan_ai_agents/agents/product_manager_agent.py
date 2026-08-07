"""Product Manager Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Product Manager Agent for Lessan AI.\n"
        "Feature request: {feature_request}\n"
        "User context: {user_context}\n"
        "Define scope, success criteria, and open questions. "
        "Do not design or implement."
    ),
    variables=("feature_request", "user_context"),
)


class ProductManagerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="ProductManagerAgent",
            role="Product Manager",
            responsibilities=[
                "Clarify and scope incoming feature requests",
                "Define acceptance criteria",
                "Balance user needs against project constraints",
                "Flag ambiguous or conflicting requirements",
            ],
            objectives=[
                "Every scoped feature has clear, testable acceptance criteria",
                "Requirements are unambiguous before reaching design/engineering",
            ],
            capabilities=[
                AgentCapability("scope_feature", "Turn a raw request into a scoped feature spec"),
                AgentCapability("define_acceptance_criteria", "Produce testable acceptance criteria"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
