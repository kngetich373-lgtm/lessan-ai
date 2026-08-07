from typing import List, Dict
from ui.agents.agent import Agent

class AgentManager:
    """Manages AI agents in Lessan AI."""
    
    def __init__(self):
        self.agents: List[Agent] = []
        self.active_agent: Agent = None

    def register_agent(self, name: str, agent_type: str, config: Dict):
        """Register a new agent."""
        agent = Agent(name, agent_type, config)
        self.agents.append(agent)
        if not self.active_agent:
            self.active_agent = agent

    def set_active_agent(self, name: str):
        """Set the active agent by name."""
        for agent in self.agents:
            if agent.name == name:
                self.active_agent = agent
                return
        raise ValueError(f"Agent '{name}' not found.")

    def get_agent_status(self, name: str) -> str:
        """Get the status of an agent."""
        for agent in self.agents:
            if agent.name == name:
                return agent.status
        return "UNKNOWN"

# Global instance
agent_manager = AgentManager()