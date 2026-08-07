"""Database Engineer Agent."""

from __future__ import annotations

from typing import Optional

from lessan_ai_agents.core.base_agent import AgentCapability, PromptTemplate
from lessan_ai_agents.core.communication import IAgentCommunicationBus
from lessan_ai_agents.core.memory import IAgentMemory

from ._role_agent import RoleAgent

_PROMPT = PromptTemplate(
    template=(
        "You are the Database Engineer Agent for Lessan AI.\n"
        "Data to persist: {data_description}\n"
        "Access patterns: {access_patterns}\n"
        "Propose a schema and storage approach consistent with local, "
        "zero-subscription execution."
    ),
    variables=("data_description", "access_patterns"),
)


class DatabaseEngineerAgent(RoleAgent):
    def __init__(
        self,
        memory: Optional[IAgentMemory] = None,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        super().__init__(
            name="DatabaseEngineerAgent",
            role="Database Engineer",
            responsibilities=[
                "Design schemas for persistent/memory-related data",
                "Plan migrations that don't disrupt existing persisted state",
                "Advise on local-first storage choices (project runs with zero subscriptions)",
            ],
            objectives=[
                "Schemas support the stated access patterns efficiently",
                "No migration silently breaks existing user data",
            ],
            capabilities=[
                AgentCapability("propose_schema", "Draft a schema for a given data description"),
                AgentCapability("plan_migration", "Outline a safe migration path for schema changes"),
            ],
            prompt_template=_PROMPT,
            memory=memory,
            communication_bus=communication_bus,
        )
