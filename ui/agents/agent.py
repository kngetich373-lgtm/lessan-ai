from typing import Dict, Any

class Agent:
    """Represents an AI agent in Lessan AI."""
    
    def __init__(self, name: str, agent_type: str, config: Dict[str, Any]):
        self.name = name
        self.agent_type = agent_type
        self.config = config
        self.status = "IDLE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.agent_type,
            "config": self.config,
            "status": self.status
        }