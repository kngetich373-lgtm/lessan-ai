"""
AgentRegistry.

Single source of truth for "which agents exist and what are they
called". Separate from AgentManager (which handles dispatch/lifecycle)
so registration/discovery can be tested and reused independently —
Interface Segregation between "know about agents" and "run agents".
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol, runtime_checkable

from .base_agent import BaseAgent


@runtime_checkable
class IAgentRegistry(Protocol):
    """Registration/lookup contract."""

    def register(self, agent: BaseAgent) -> None: ...

    def unregister(self, name: str) -> bool: ...

    def get(self, name: str) -> Optional[BaseAgent]: ...

    def list_agents(self) -> list[BaseAgent]: ...

    def find_by_capability(self, capability_name: str) -> list[BaseAgent]: ...


class AgentRegistry:
    """Default, dependency-free implementation of IAgentRegistry."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' is already registered")
        agent.initialize()
        self._agents[agent.name] = agent

    def unregister(self, name: str) -> bool:
        return self._agents.pop(name, None) is not None

    def get(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def list_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def find_by_capability(self, capability_name: str) -> list[BaseAgent]:
        return [
            agent
            for agent in self._agents.values()
            if any(cap.name == capability_name for cap in agent.capabilities)
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __iter__(self) -> Iterable[BaseAgent]:
        return iter(self._agents.values())
