"""Workspace registry for Lessan AI."""

import threading
from typing import Dict, List, Optional, Type

from core.event_bus import event_bus
from core.logging import get_logger
from workspaces.base_workspace import BaseWorkspace

logger = get_logger("workspaces.registry")


class WorkspaceRegistry:
    """Registers workspace classes and manages workspace instances.

    Supports:
      - Registration of workspace classes by name.
      - Discovery of registered workspace types.
      - Instance creation, tracking, and retrieval.
    """

    def __init__(self) -> None:
        self._classes: Dict[str, Type[BaseWorkspace]] = {}
        self._instances: Dict[str, BaseWorkspace] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(self, workspace_class: Type[BaseWorkspace]) -> Type[BaseWorkspace]:
        """Register a workspace class. Returns the class for decorator use."""
        name = getattr(workspace_class, "name", None)
        if not name:
            raise ValueError(f"Workspace class {workspace_class.__name__} needs a 'name' attribute.")
        with self._lock:
            self._classes[name] = workspace_class
        logger.info(f"Registered workspace type: {name}")
        return workspace_class

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._classes.pop(name, None) is not None

    # ------------------------------------------------------------------ #
    # Creation
    # ------------------------------------------------------------------ #
    def create(self, name: str, config: Optional[dict] = None) -> BaseWorkspace:
        """Create an instance of a registered workspace class."""
        with self._lock:
            cls = self._classes.get(name)
        if cls is None:
            raise KeyError(f"Workspace type '{name}' is not registered.")

        instance = cls()
        instance.initialize(config or {})
        with self._lock:
            self._instances[instance.name] = instance
        return instance

    def get(self, name: str) -> Optional[BaseWorkspace]:
        with self._lock:
            return self._instances.get(name)

    def get_or_create(self, name: str, config: Optional[dict] = None) -> BaseWorkspace:
        existing = self.get(name)
        if existing is not None:
            return existing
        return self.create(name, config)

    def destroy(self, name: str) -> bool:
        """Destroy an instance and remove it from tracking."""
        with self._lock:
            instance = self._instances.pop(name, None)
        if instance is None:
            return False
        try:
            instance.destroy()
        except Exception:  # noqa: BLE001
            logger.error(f"Error destroying workspace '{name}'", exc_info=True)
        return True

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def available(self) -> List[str]:
        """Return names of registered-but-not-yet-instantiated workspace types."""
        with self._lock:
            return sorted(self._classes)

    def active_instances(self) -> List[BaseWorkspace]:
        with self._lock:
            return [w for w in self._instances.values() if w.status == "activated"]

    def all_instances(self) -> List[BaseWorkspace]:
        with self._lock:
            return list(self._instances.values())

    def manifest(self) -> List[dict]:
        """Return a list of workspace manifests (union of types + instances)."""
        types = []
        with self._lock:
            for name, cls in self._classes.items():
                types.append(
                    {
                        "name": name,
                        "display_name": getattr(cls, "display_name", name),
                        "description": getattr(cls, "description", ""),
                        "icon": getattr(cls, "icon", "◈"),
                        "color": getattr(cls, "color", "#8b5cf6"),
                        "status": "available",
                    }
                )
            seen = {t["name"] for t in types}
            for ws in self._instances.values():
                manifest = ws.to_manifest()
                if manifest["name"] not in seen:
                    types.append(manifest)
                    seen.add(manifest["name"])
        return types


# Global registry
workspace_registry = WorkspaceRegistry()