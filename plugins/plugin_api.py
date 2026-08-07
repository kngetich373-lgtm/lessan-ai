"""PluginAPI — sandboxed, provided services that plugins can use."""

from typing import Any, Dict, List, Optional

from core.event_bus import event_bus
from core.logging import get_logger
from core.state import state


class PluginAPI:
    """Safe, curated interface the core exposes to plugins.

    Plugins receive an instance of this API during on_load and can use it to:
      - emit/listen to events
      - read/write scoped state
      - log
      - access the workspace/agent registries (read-only)
      - run simple file operations within a sandbox root
    """

    def __init__(self, plugin_name: str, sandbox_root: str = "") -> None:
        self.plugin_name = plugin_name
        self.sandbox_root = sandbox_root or ""
        self.logger = get_logger(f"plugin.{plugin_name}.api")

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    def emit(self, event_type: str, data: Dict[str, Any] = None) -> None:
        event_bus.emit(event_type, data or {})

    def subscribe(self, event_type: str, handler: Any) -> None:
        event_bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        event_bus.unsubscribe(event_type, handler)

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    def state_get(self, key: str, default: Any = None) -> Any:
        return state.get(f"plugin.{self.plugin_name}.{key}", default)

    def state_set(self, key: str, value: Any) -> None:
        state.set(f"plugin.{self.plugin_name}.{key}", value)

    # ------------------------------------------------------------------ #
    # Registries (read-only)
    # ------------------------------------------------------------------ #
    def available_workspaces(self) -> List[str]:
        from workspaces.workspace_registry import workspace_registry

        return workspace_registry.available()

    def available_agents(self) -> List[str]:
        from agents.framework.agent_registry import agent_registry

        return agent_registry.available()

    def available_plugins(self) -> List[str]:
        from plugins.plugin_registry import plugin_registry

        return plugin_registry.available()

    # ------------------------------------------------------------------ #
    # Sandboxed file access
    # ------------------------------------------------------------------ #
    def _resolve(self, rel_path: str) -> str:
        import os

        if not self.sandbox_root:
            raise PermissionError("This plugin has no file sandbox.")
        full = os.path.realpath(os.path.join(self.sandbox_root, rel_path))
        root = os.path.realpath(self.sandbox_root)
        if not full.startswith(root):
            raise PermissionError(f"Path '{rel_path}' is outside the sandbox.")
        return full

    def read_file(self, rel_path: str) -> str:
        with open(self._resolve(rel_path), "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, rel_path: str, content: str) -> None:
        import os

        full = self._resolve(rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)

    # ------------------------------------------------------------------ #
    # Misc helpers
    # ------------------------------------------------------------------ #
    def log(self, message: str, level: str = "info") -> None:
        getattr(self.logger, level, self.logger.info)(message)