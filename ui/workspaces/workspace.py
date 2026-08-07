from typing import Dict, Any

class Workspace:
    """Represents a workspace configuration in Lessan AI."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "config": self.config}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workspace":
        return cls(data["name"], data["config"])