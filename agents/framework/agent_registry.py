"""AgentRegistry — registers and instantiates agent classes."""

import threading
from typing import Dict, List, Optional, Type

from core.logging import get_logger
from agents.framework.base_agent import BaseAgent

logger = get_logger("agents.registry")


class AgentRegistry:
    """Registry of agent classes by name."""

    def __init__(self) -> None:
        self._classes: Dict[str, Type[BaseAgent]] = {}
        self._instances: Dict[str, BaseAgent] = {}
        self._lock = threading.RLock()

    def register(self, agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
        name = getattr(agent_class, "name", None)
        if not name:
            raise ValueError(f"Agent class {agent_class.__name__} needs a 'name' attribute.")
        with self._lock:
            self._classes[name] = agent_class
        logger.info(f"Registered agent type: {name}")
        return agent_class

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._classes.pop(name, None) is not None

    def create(self, name: str, config: Optional[dict] = None) -> BaseAgent:
        with self._lock:
            cls = self._classes.get(name)
        if cls is None:
            raise KeyError(f"Agent type '{name}' is not registered.")
        instance = cls()
        instance.initialize(config or {})
        with self._lock:
            self._instances[instance.name] = instance
        return instance

    def get(self, name: str) -> Optional[BaseAgent]:
        with self._lock:
            return self._instances.get(name)

    def get_or_create(self, name: str, config: Optional[dict] = None) -> BaseAgent:
        existing = self.get(name)
        if existing is not None:
            return existing
        return self.create(name, config)

    def destroy(self, name: str) -> bool:
        with self._lock:
            instance = self._instances.pop(name, None)
        if instance is None:
            return False
        try:
            instance.destroy()
        except Exception:
            logger.error(f"Error destroying agent '{name}'", exc_info=True)
        return True

    def available(self) -> List[str]:
        with self._lock:
            return sorted(self._classes)

    def active(self) -> List[BaseAgent]:
        with self._lock:
            return [a for a in self._instances.values() if a.status.value in ("running", "idle")]

    def all_instances(self) -> List[BaseAgent]:
        with self._lock:
            return list(self._instances.values())

    def manifest(self) -> List[dict]:
        types = []
        with self._lock:
            for name, cls in self._classes.items():
                types.append({
                    "name": name,
                    "display_name": getattr(cls, "display_name", name),
                    "description": getattr(cls, "description", ""),
                    "version": getattr(cls, "version", "1.0.0"),
                    "icon": getattr(cls, "icon", "◈"),
                    "color": getattr(cls, "color", "#8b5cf6"),
                    "status": "available",
                })
            seen = {t["name"] for t in types}
            for agent in self._instances.values():
                m = agent.to_manifest()
                if m["name"] not in seen:
                    types.append(m)
                    seen.add(m["name"])
        return types


# Global registry
agent_registry = AgentRegistry()