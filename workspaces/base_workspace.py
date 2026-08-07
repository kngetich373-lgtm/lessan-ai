"""Base workspace class with full lifecycle management for Lessan AI."""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import event_bus
from core.logging import get_logger
from core.state import state


class WorkspaceState(Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    ACTIVATED = "activated"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    DESTROYED = "destroyed"


@dataclass
class ToolSpec:
    """Describes a tool exposed by a workspace."""

    name: str
    description: str
    handler: Callable[..., Any]
    parameters: Dict[str, Any] = field(default_factory=dict)


class BaseWorkspace:
    """Base class for all Lessan AI workspaces.

    Handles the full workspace lifecycle:
      create → initialize → activate → (suspend/deactivate) → destroy

    Each workspace can expose tools, register event handlers, and publish
    state changes to the global state store.
    """

    # Metadata subclasses should override
    name: str = "base"
    display_name: str = "Base Workspace"
    description: str = ""
    icon: str = "◈"
    color: str = "#8b5cf6"
    order: int = 100
    requires_auth: bool = False

    def __init__(self) -> None:
        self._state_enum = WorkspaceState.CREATED
        self._tools: Dict[str, ToolSpec] = {}
        self._event_handlers: List[tuple[str, Callable[..., Any]]] = []
        self._lock = threading.RLock()
        self._started_at: Optional[datetime] = None
        self._session_data: Dict[str, Any] = {}
        self.logger = get_logger(f"workspace.{self.name}")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the workspace with optional configuration.

        Subclasses should override :meth:`on_initialize` rather than this
        method directly.
        """
        with self._lock:
            if self._state_enum not in (WorkspaceState.CREATED,):
                raise RuntimeError(
                    f"Cannot initialize workspace '{self.name}' from state "
                    f"'{self._state_enum.value}'"
                )
            self._config = config or {}
            self.on_initialize(self._config)
            self._state_enum = WorkspaceState.INITIALIZED
            self._register_default_events()
            self.logger.info(f"Initialized workspace '{self.name}'")

    def activate(self) -> None:
        """Activate the workspace (make it the active workspace)."""
        with self._lock:
            if self._state_enum in (WorkspaceState.DESTROYED,):
                raise RuntimeError(f"Cannot activate destroyed workspace '{self.name}'")
            if self._state_enum == WorkspaceState.CREATED:
                self.initialize()
            self.on_activate()
            self._state_enum = WorkspaceState.ACTIVATED
            self._started_at = datetime.now()
        state.update("workspace.active", {"name": self.name, "started_at": str(self._started_at)})
        event_bus.emit("workspace.activated", {"name": self.name})
        self.logger.info(f"Activated workspace '{self.name}'")

    def suspend(self) -> None:
        """Suspend the workspace (pause without full teardown)."""
        with self._lock:
            if self._state_enum in (WorkspaceState.DESTROYED, WorkspaceState.CREATED):
                return
            self.on_suspend()
            self._state_enum = WorkspaceState.SUSPENDED
        event_bus.emit("workspace.suspended", {"name": self.name})
        self.logger.info(f"Suspended workspace '{self.name}'")

    def resume(self) -> None:
        """Resume a suspended workspace."""
        with self._lock:
            if self._state_enum != WorkspaceState.SUSPENDED:
                return
            self.on_resume()
            self._state_enum = WorkspaceState.ACTIVATED
            self._started_at = datetime.now()
        event_bus.emit("workspace.activated", {"name": self.name})
        self.logger.info(f"Resumed workspace '{self.name}'")

    def deactivate(self) -> None:
        """Deactivate the workspace (hide but keep state)."""
        with self._lock:
            if self._state_enum in (WorkspaceState.DESTROYED, WorkspaceState.CREATED):
                return
            self.on_deactivate()
            self._state_enum = WorkspaceState.DEACTIVATED
            self._started_at = None
        event_bus.emit("workspace.deactivated", {"name": self.name})
        self.logger.info(f"Deactivated workspace '{self.name}'")

    def destroy(self) -> None:
        """Destroy the workspace and release all resources."""
        with self._lock:
            if self._state_enum == WorkspaceState.CREATED:
                self._state_enum = WorkspaceState.DESTROYED
                return
            self.on_destroy()
            self._unregister_events()
            self._state_enum = WorkspaceState.DESTROYED
        event_bus.emit("workspace.destroyed", {"name": self.name})
        self.logger.info(f"Destroyed workspace '{self.name}'")

    # ------------------------------------------------------------------ #
    # Hooks for subclasses
    # ------------------------------------------------------------------ #
    def on_initialize(self, config: Dict[str, Any]) -> None:
        """Override: set up workspace resources and tools."""

    def on_activate(self) -> None:
        """Override: run when the workspace becomes active."""

    def on_suspend(self) -> None:
        """Override: run when the workspace is suspended."""

    def on_resume(self) -> None:
        """Override: run when a suspended workspace resumes."""

    def on_deactivate(self) -> None:
        """Override: run when the workspace is deactivated."""

    def on_destroy(self) -> None:
        """Override: clean up workspace resources."""

    # ------------------------------------------------------------------ #
    # Tool registration
    # ------------------------------------------------------------------ #
    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool callable that this workspace provides."""
        tool = ToolSpec(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters or {},
        )
        with self._lock:
            self._tools[name] = tool
        self.logger.debug(f"Registered tool '{name}' in workspace '{self.name}'")

    def unregister_tool(self, name: str) -> bool:
        with self._lock:
            return self._tools.pop(name, None) is not None

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        with self._lock:
            return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in self._tools.values()
            ]

    def execute_tool(self, name: str, **kwargs: Any) -> Any:
        """Execute a registered tool by name with keyword arguments."""
        tool = self.get_tool(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found in workspace '{self.name}'")
        return tool.handler(**kwargs)

    # ------------------------------------------------------------------ #
    # Event handling
    # ------------------------------------------------------------------ #
    def _register_default_events(self) -> None:
        # Subclasses can override for workspace-specific event handling.
        pass

    def _unregister_events(self) -> None:
        for event_name, handler in self._event_handlers:
            event_bus.unsubscribe(event_name, handler)
        self._event_handlers.clear()

    def on_event(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Subscribe to a core event bus event."""
        event_bus.subscribe(event_name, handler)
        self._event_handlers.append((event_name, handler))

    # ------------------------------------------------------------------ #
    # Session data
    # ------------------------------------------------------------------ #
    def set_session(self, key: str, value: Any) -> None:
        self._session_data[key] = value

    def get_session(self, key: str, default: Any = None) -> Any:
        return self._session_data.get(key, default)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def status(self) -> str:
        return self._state_enum.value

    @property
    def is_active(self) -> bool:
        return self._state_enum in (WorkspaceState.ACTIVATED,)

    @property
    def config(self) -> Dict[str, Any]:
        return getattr(self, "_config", {})

    def to_manifest(self) -> Dict[str, Any]:
        """Return a serializable manifest of the workspace."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "status": self.status,
            "tools": [t["name"] for t in self.list_tools()],
        }