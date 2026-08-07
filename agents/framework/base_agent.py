"""BaseAgent — lifecycle, capabilities, and tool exposure for Lessan AI agents."""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import event_bus
from core.logging import get_logger
from core.state import state


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentTask:
    """A unit of work for an agent."""

    description: str
    priority: int = 1
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: AgentStatus = AgentStatus.IDLE
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AgentCapability:
    """A discrete capability an agent can perform."""

    name: str
    description: str
    handler: Callable[..., Any]
    parameters: Dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    """Base class for all Lessan AI agents.

    Provides:
      - Lifecycle: initialize → run → pause → resume → stop → destroy
      - Capability registration and execution
      - Task queue management
      - Event bus integration
    """

    name: str = "base"
    display_name: str = "Base Agent"
    description: str = ""
    version: str = "1.0.0"
    color: str = "#8b5cf6"
    icon: str = "◈"

    def __init__(self) -> None:
        self.status = AgentStatus.IDLE
        self._capabilities: Dict[str, AgentCapability] = {}
        self._tasks: List[AgentTask] = []
        self._lock = threading.RLock()
        self._event_handlers: List[tuple[str, Callable[..., Any]]] = []
        self.logger = get_logger(f"agent.{self.name}")
        self._session: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self.on_initialize(self._config)
        self.status = AgentStatus.IDLE
        self.logger.info(f"Initialized agent '{self.name}'")

    def run(self, task_description: str) -> Any:
        task = AgentTask(description=task_description)
        with self._lock:
            self._tasks.append(task)
        self.status = AgentStatus.RUNNING
        event_bus.emit("agent.started", {"agent": self.name, "task": task_description})
        try:
            result = self.on_run(task)
            task.result = result
            task.status = AgentStatus.COMPLETED
            self.status = AgentStatus.IDLE
            event_bus.emit("agent.completed", {"agent": self.name, "task": task_description})
            return result
        except Exception as exc:
            task.error = str(exc)
            task.status = AgentStatus.FAILED
            self.status = AgentStatus.FAILED
            event_bus.emit("agent.failed", {"agent": self.name, "error": str(exc)})
            raise

    def pause(self) -> None:
        if self.status == AgentStatus.RUNNING:
            self.status = AgentStatus.PAUSED
            self.on_pause()
            event_bus.emit("agent.paused", {"agent": self.name})

    def resume(self) -> None:
        if self.status == AgentStatus.PAUSED:
            self.status = AgentStatus.RUNNING
            self.on_resume()
            event_bus.emit("agent.resumed", {"agent": self.name})

    def stop(self) -> None:
        self.on_stop()
        self.status = AgentStatus.STOPPED
        event_bus.emit("agent.stopped", {"agent": self.name})

    def destroy(self) -> None:
        self.on_destroy()
        for event_name, handler in self._event_handlers:
            event_bus.unsubscribe(event_name, handler)
        self._event_handlers.clear()
        self.status = AgentStatus.STOPPED
        self.logger.info(f"Destroyed agent '{self.name}'")

    # ------------------------------------------------------------------ #
    # Hooks
    # ------------------------------------------------------------------ #
    def on_initialize(self, config: Dict[str, Any]) -> None: ...
    def on_run(self, task: AgentTask) -> Any: ...
    def on_pause(self) -> None: ...
    def on_resume(self) -> None: ...
    def on_stop(self) -> None: ...
    def on_destroy(self) -> None: ...

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #
    def register_capability(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._capabilities[name] = AgentCapability(
                name=name, description=description,
                handler=handler, parameters=parameters or {},
            )

    def unregister_capability(self, name: str) -> bool:
        with self._lock:
            return self._capabilities.pop(name, None) is not None

    def has_capability(self, name: str) -> bool:
        with self._lock:
            return name in self._capabilities

    def execute_capability(self, name: str, **kwargs: Any) -> Any:
        cap = self.get_capability(name)
        if cap is None:
            raise KeyError(f"Capability '{name}' not found on agent '{self.name}'")
        return cap.handler(**kwargs)

    def get_capability(self, name: str) -> Optional[AgentCapability]:
        with self._lock:
            return self._capabilities.get(name)

    def list_capabilities(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"name": c.name, "description": c.description, "parameters": c.parameters}
                for c in self._capabilities.values()
            ]

    # ------------------------------------------------------------------ #
    # Task management
    # ------------------------------------------------------------------ #
    def add_task(self, description: str, priority: int = 1) -> AgentTask:
        task = AgentTask(description=description, priority=priority)
        with self._lock:
            self._tasks.append(task)
        return task

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        with self._lock:
            for t in self._tasks:
                if t.task_id == task_id:
                    return t
        return None

    def pending_tasks(self) -> List[AgentTask]:
        with self._lock:
            return [t for t in self._tasks if t.status in (AgentStatus.IDLE, AgentStatus.WAITING)]

    def clear_finished_tasks(self) -> int:
        with self._lock:
            finished = [t for t in self._tasks if t.status in (AgentStatus.COMPLETED, AgentStatus.FAILED)]
            for t in finished:
                self._tasks.remove(t)
            return len(finished)

    # ------------------------------------------------------------------ #
    # Events & session
    # ------------------------------------------------------------------ #
    def on_event(self, event_name: str, handler: Callable[..., Any]) -> None:
        event_bus.subscribe(event_name, handler)
        self._event_handlers.append((event_name, handler))

    def set_session(self, key: str, value: Any) -> None:
        self._session[key] = value

    def get_session(self, key: str, default: Any = None) -> Any:
        return self._session.get(key, default)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def tasks(self) -> List[AgentTask]:
        with self._lock:
            return list(self._tasks)

    def to_manifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "status": self.status.value,
            "capabilities": [c["name"] for c in self.list_capabilities()],
        }