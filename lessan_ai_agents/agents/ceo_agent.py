"""
CEO Agent.

Coordinates work across the other ten agents. Per project scope this
agent explicitly does NOT generate software and does NOT implement any
concrete multi-step workflow — it only has the capability to *delegate*
a request to another named agent via the communication bus. Any actual
sequencing of "who does what when" is left to a future orchestration
layer outside this framework's scope.
"""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, AgentContext, PromptTemplate
from lessan_ai_agents.core.communication import AgentMessage, IAgentCommunicationBus, MessageType
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the CEO Agent for Lessan AI.\n"
        "Objective under consideration: {objective}\n"
        "Constraints: {constraints}\n"
        "Coordinate — do not implement. Identify which specialist "
        "agent(s) this belongs to and what each needs to know."
    ),
    variables=("objective", "constraints"),
)


class CEOAgent(RoleAgent):
    """Coordination-only agent. Sits above the other ten agents."""

    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="CEOAgent",
            role="Chief Executive Officer",
            responsibilities=[
                "Interpret high-level goals and translate them into requests for specialist agents",
                "Coordinate handoffs between agents",
                "Track overall project direction at a summary level",
                "Resolve conflicting priorities raised by other agents",
            ],
            objectives=[
                "Ensure every request reaches the right specialist agent",
                "Keep coordination overhead minimal",
                "Never perform specialist work itself",
            ],
            capabilities=[
                AgentCapability("delegate", "Route a request to a named specialist agent"),
                AgentCapability("prioritize", "Rank competing requests by stated priority"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )

    def delegate(self, target_agent: str, objective: str, constraints: str = "") -> AgentMessage:
        """Coordinate-only action: publish a REQUEST to another agent.
        Does not execute the target agent itself and does not decide a
        multi-step plan — a single hand-off per call, by design.
        """
        if self.communication_bus is None:
            raise RuntimeError("CEOAgent has no communication bus attached")
        message = AgentMessage(
            sender=self.name,
            message_type=MessageType.REQUEST,
            recipient=target_agent,
            payload={"objective": objective, "constraints": constraints},
        )
        self.communication_bus.publish(message)
        return message
