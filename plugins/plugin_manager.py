"""PluginManager — orchestrates plugin lifecycle and discovery."""

import importlib
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger
from plugins.plugin_base import PluginBase
from plugins.plugin_registry import plugin_registry
from plugins.plugin_api import PluginAPI

logger = get_logger("plugins.manager")


class PluginManager:
    """Manages plugin discovery, loading, and lifecycle.

    Supports:
      - Auto-discovery from a plugin directory
      - Manual registration of plugin classes
      - Enable/disable individual plugins
      - Scoped state and file sandbox per plugin
    """

    def __init__(self, plugin_dir: str = "plugins") -> None:
        self.plugin_dir = Path(plugin_dir)
        self._sandbox_root = ""
        self._lock = threading.RLock()

    def set_sandbox(self, root: str) -> None:
        self._sandbox_root = root

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    def discover(self) -> List[str]:
        discovered = []
        if not self.plugin_dir.exists():
            return discovered

        for file in self.plugin_dir.glob("*.py"):
            if file.name.startswith("_") or file.name == "plugin_base.py":
                continue
            module_name = f"plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)
                for attr in dir(module):
                    obj = getattr(module, attr)
                    if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                        plugin_registry.register(obj)
                        discovered.append(obj.name)
            except Exception as exc:
                logger.error(f"Failed to load plugin from {module_name}: {exc}")
        return discovered

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def load(self, name: str, config: Optional[Dict[str, Any]] = None) -> PluginBase:
        plugin = plugin_registry.create(name, config)
        plugin.api = PluginAPI(name, self._sandbox_root)
        return plugin

    def enable(self, name: str) -> bool:
        plugin = plugin_registry.get(name)
        if plugin is None:
            return False
        plugin.enable()
        return True

    def disable(self, name: str) -> bool:
        plugin = plugin_registry.get(name)
        if plugin is None:
            return False
        plugin.disable()
        return True

    def unload(self, name: str) -> bool:
        return plugin_registry.destroy(name)

    def reload(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[PluginBase]:
        self.unload(name)
        try:
            return self.load(name, config)
        except KeyError:
            return None

    # ------------------------------------------------------------------ #
    # Bulk operations
    # ------------------------------------------------------------------ #
    def load_all(self, config: Optional[Dict[str, Any]] = None) -> List[str]:
        loaded = []
        for name in plugin_registry.available():
            try:
                self.load(name, config)
                loaded.append(name)
            except Exception as exc:
                logger.error(f"Failed to load plugin '{name}': {exc}")
        return loaded

    def enable_all(self) -> List[str]:
        enabled = []
        for plugin in plugin_registry.all_instances():
            plugin.enable()
            enabled.append(plugin.name)
        return enabled

    def disable_all(self) -> List[str]:
        disabled = []
        for plugin in plugin_registry.all_instances():
            plugin.disable()
            disabled.append(plugin.name)
        return disabled

    def unload_all(self) -> List[str]:
        unloaded = []
        for name in plugin_registry.available():
            if plugin_registry.destroy(name):
                unloaded.append(name)
        return unloaded

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def status(self) -> Dict[str, str]:
        return {p.name: "enabled" if p.enabled else "loaded" for p in plugin_registry.all_instances()}

    def manifests(self) -> List[Dict[str, Any]]:
        return plugin_registry.manifest()


# Global manager
plugin_manager = PluginManager()