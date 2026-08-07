"""AgentManager — orchestration of agents in Lessan AI."""

import threading
from typing import Any, Dict, List, Optional

from core.event_bus import event_bus
from core.logging import get_logger
from core.state import state
from agents.framework.agent_registry import agent_registry
from agents.framework.base_agent import BaseAgent
from agents.framework.messenger import agent_messenger

logger = get_logger("agents.manager")


class AgentManager:
    """Manages agent lifecycle, dispatch, and coordination.

    Responsibilities:
      - Create/retrieve agents through the registry.
      - Dispatch tasks to the appropriate agent.
      - Relay messages between agents via the messenger.
      - Expose status in the global state store.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dispatch_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Agent lifecycle
    # ------------------------------------------------------------------ #
    def spawn(self, name: str, config: Optional[dict] = None) -> BaseAgent:
        """Create (or reuse) an agent instance by registered type."""
        agent = agent_registry.get_or_create(name, config)
        state.update("agents.status", {name: agent.status.value})
        return agent

    def shutdown(self, name: str) -> bool:
        ok = agent_registry.destroy(name)
        if ok:
            state.delete(f"agents.status.{name}")
        return ok

    def get(self, name: str) -> Optional[BaseAgent]:
        return agent_registry.get(name)

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    def dispatch(self, agent_name: str, task_description: str) -> Any:
        """Run a task on a named agent synchronously."""
        agent = self.spawn(agent_name)
        result = agent.run(task_description)
        with self._lock:
            self._dispatch_history.append({
                "agent": agent_name,
                "task": task_description,
                "status": "completed",
                "result": result,
            })
        state.update("agents.status", {agent_name: agent.status.value})
        return result

    def dispatch_async(self, agent_name: str, task_description: str) -> threading.Thread:
        """Run a task on a named agent in a background thread."""
        def _runner() -> None:
            try:
                self.dispatch(agent_name, task_description)
            except Exception as exc:
                logger.error(f"Async dispatch to '{agent_name}' failed: {exc}")

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return thread

    # ------------------------------------------------------------------ #
    # Messaging
    # ------------------------------------------------------------------ #
    def send(self, sender: str, recipient: str, content: Any) -> Any:
        return agent_messenger.send(sender, recipient, content)

    def request(self, sender: str, recipient: str, content: Any, timeout: float = 10.0) -> Any:
        return agent_messenger.request(sender, recipient, content, timeout=timeout)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def status(self) -> Dict[str, str]:
        return {a.name: a.status.value for a in agent_registry.all_instances()}

    def available_agents(self) -> List[str]:
        return agent_registry.available()

    def manifests(self) -> List[dict]:
        return agent_registry.manifest()

    def dispatch_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return self._dispatch_history[-limit:]


# Global manager
agent_manager = AgentManager()