"""QA Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the QA Engineer Agent for Lessan AI.\n"
        "Feature/spec under test: {feature_spec}\n"
        "Acceptance criteria: {acceptance_criteria}\n"
        "Propose a test plan (unit, integration, cross-platform) "
        "covering the acceptance criteria."
    ),
    variables=("feature_spec", "acceptance_criteria"),
)


class QAEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="QAEngineerAgent",
            role="QA Engineer",
            responsibilities=[
                "Design test plans against stated acceptance criteria",
                "Verify cross-platform behavior (Windows/macOS/Linux)",
                "Flag untestable or ambiguous requirements back to Product Manager",
            ],
            objectives=[
                "Every acceptance criterion maps to at least one test case",
                "Regressions in existing UI/chat surfaces are caught before release",
            ],
            capabilities=[
                AgentCapability("design_test_plan", "Produce a structured test plan from acceptance criteria"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
