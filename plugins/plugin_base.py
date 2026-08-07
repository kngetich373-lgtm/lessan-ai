"""PluginBase — life cycle, capabilities and event integration for Lessan plugins."""

import threading
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import event_bus
from core.logging import get_logger


class PluginBase:
    """Base class for all Lessan AI plugins.

    Provides life cycle hooks (load → enable → event → disable → unload),
    capability registration, and event bus integration. Subclasses set
    ``name``, ``version`` and override the hooks.
    """

    name: str = "base"
    display_name: str = "Base Plugin"
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    min_core_version: str = "0.1.0"

    def __init__(self) -> None:
        self._enabled = False
        self._capabilities: Dict[str, Callable[..., Any]] = {}
        self._event_handlers: List[tuple[str, Callable[..., Any]]] = []
        self._lock = threading.RLock()
        self.logger = get_logger(f"plugin.{self.name}")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def load(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self.on_load(self._config)
        self.on_event_proxy = self._event_proxy
        self.logger.info(f"Loaded plugin '{self.name}' v{self.version}")

    def enable(self) -> None:
        if self._enabled:
            return
        self.on_enable()
        self._enabled = True
        for event_name, handler in self._event_handlers:
            event_bus.subscribe(event_name, handler)
        self.logger.info(f"Enabled plugin '{self.name}'")

    def disable(self) -> None:
        if not self._enabled:
            return
        for event_name, handler in self._event_handlers:
            event_bus.unsubscribe(event_name, handler)
        self.on_disable()
        self._enabled = False
        self.logger.info(f"Disabled plugin '{self.name}'")

    def unload(self) -> None:
        self.disable()
        self.on_unload()
        self.logger.info(f"Unloaded plugin '{self.name}'")

    # ------------------------------------------------------------------ #
    # Hooks
    # ------------------------------------------------------------------ #
    def on_load(self, config: Dict[str, Any]) -> None: ...
    def on_enable(self) -> None: ...
    def on_disable(self) -> None: ...
    def on_unload(self) -> None: ...

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #
    def register_capability(self, name: str, handler: Callable[..., Any]) -> None:
        with self._lock:
            self._capabilities[name] = handler

    def unregister_capability(self, name: str) -> bool:
        with self._lock:
            return self._capabilities.pop(name, None) is not None

    def execute_capability(self, name: str, **kwargs: Any) -> Any:
        with self._lock:
            handler = self._capabilities.get(name)
        if handler is None:
            raise KeyError(f"Capability '{name}' not found on plugin '{self.name}'")
        return handler(**kwargs)

    def list_capabilities(self) -> List[str]:
        with self._lock:
            return list(self._capabilities)

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    def on_event(self, event_type: str, data: dict) -> None:
        """Override: called when subscribed events fire."""

    def subscribe(self, event_name: str, handler: Callable[..., Any]) -> None:
        self._event_handlers.append((event_name, handler))
        if self._enabled:
            event_bus.subscribe(event_name, handler)

    def _event_proxy(self, event_type: str, data: dict) -> None:
        try:
            self.on_event(event_type, data)
        except Exception:
            self.logger.error(f"Plugin '{self.name}' failed handling '{event_type}'", exc_info=True)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def config(self) -> Dict[str, Any]:
        return getattr(self, "_config", {})

    def to_manifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "enabled": self._enabled,
            "capabilities": self.list_capabilities(),
        }