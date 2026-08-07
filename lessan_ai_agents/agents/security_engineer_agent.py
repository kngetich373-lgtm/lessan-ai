"""Security Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Security Engineer Agent for Lessan AI.\n"
        "Component under review: {component}\n"
        "Trust boundaries: {trust_boundaries}\n"
        "Identify risks (e.g. local system-control access, API key "
        "handling, signed-package integrity) and mitigations. Do not "
        "produce exploit code."
    ),
    variables=("component", "trust_boundaries"),
)


class SecurityEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="SecurityEngineerAgent",
            role="Security Engineer",
            responsibilities=[
                "Review designs for risk, especially where the assistant has system-control access",
                "Advise on safe handling of API keys and credentials",
                "Review packaging/distribution integrity (e.g. signed apt repo)",
            ],
            objectives=[
                "No design grants broader system access than the feature requires",
                "Credentials are never persisted in plaintext by recommended designs",
            ],
            capabilities=[
                AgentCapability("review_risk", "Identify security risks in a proposed component"),
                AgentCapability("recommend_mitigation", "Propose mitigations for an identified risk"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
