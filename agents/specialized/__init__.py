# Specialized agents for Lessan AI.

from agents.specialized.executive_agent import ExecutiveAgent
from agents.specialized.engineering_agent import EngineeringAgent
from agents.specialized.security_agent import SecurityAgent
from agents.specialized.research_agent import ResearchAgent
from agents.specialized.automation_agent import AutomationAgent


def register_all() -> None:
    """Register all specialized agents into the global registry."""
    from agents.framework.agent_registry import agent_registry

    agent_registry.register(ExecutiveAgent)
    agent_registry.register(EngineeringAgent)
    agent_registry.register(SecurityAgent)
    agent_registry.register(ResearchAgent)
    agent_registry.register(AutomationAgent)