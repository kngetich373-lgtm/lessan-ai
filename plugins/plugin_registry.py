"""PluginRegistry — registers plugin classes and tracks loaded instances."""

import threading
from typing import Dict, List, Optional, Type

from core.logging import get_logger
from plugins.plugin_base import PluginBase

logger = get_logger("plugins.registry")


class PluginRegistry:
    """Registry of plugin classes and their loaded instances."""

    def __init__(self) -> None:
        self._classes: Dict[str, Type[PluginBase]] = {}
        self._instances: Dict[str, PluginBase] = {}
        self._lock = threading.RLock()

    def register(self, plugin_class: Type[PluginBase]) -> Type[PluginBase]:
        name = getattr(plugin_class, "name", None)
        if not name:
            raise ValueError(f"Plugin class {plugin_class.__name__} needs a 'name' attribute.")
        with self._lock:
            self._classes[name] = plugin_class
        logger.info(f"Registered plugin type: {name} v{getattr(plugin_class, 'version', '?')}")
        return plugin_class

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._classes.pop(name, None) is not None

    def create(self, name: str, config: Optional[dict] = None) -> PluginBase:
        with self._lock:
            cls = self._classes.get(name)
        if cls is None:
            raise KeyError(f"Plugin type '{name}' is not registered.")
        instance = cls()
        instance.load(config or {})
        with self._lock:
            self._instances[instance.name] = instance
        return instance

    def get(self, name: str) -> Optional[PluginBase]:
        with self._lock:
            return self._instances.get(name)

    def get_or_create(self, name: str, config: Optional[dict] = None) -> PluginBase:
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
            instance.unload()
        except Exception:
            logger.error(f"Error unloading plugin '{name}'", exc_info=True)
        return True

    def available(self) -> List[str]:
        with self._lock:
            return sorted(self._classes)

    def all_instances(self) -> List[PluginBase]:
        with self._lock:
            return list(self._instances.values())

    def manifest(self) -> List[dict]:
        types = []
        with self._lock:
            for name, cls in self._classes.items():
                types.append({
                    "name": name,
                    "display_name": getattr(cls, "display_name", name),
                    "version": getattr(cls, "version", "1.0.0"),
                    "description": getattr(cls, "description", ""),
                    "author": getattr(cls, "author", ""),
                    "status": "available",
                })
            seen = {t["name"] for t in types}
            for plugin in self._instances.values():
                m = plugin.to_manifest()
                if m["name"] not in seen:
                    types.append(m)
                    seen.add(m["name"])
        return types


# Global registry
plugin_registry = PluginRegistry()