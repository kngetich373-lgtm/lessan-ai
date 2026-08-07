import importlib
import os
from pathlib import Path
from typing import List, Type
from ui.plugins.plugin_base import PluginBase

class PluginManager:
    """Manages the lifecycle of plugins in Lessan AI."""
    
    def __init__(self, plugin_dir: str = "ui/plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugins: List[PluginBase] = []

    def discover_plugins(self):
        """Discover and load plugins from the plugin directory."""
        for file in self.plugin_dir.glob("*.py"):
            if file.name == "plugin_base.py" or file.stem.startswith("_"):
                continue
            module_name = f"ui.plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)
                for attr in dir(module):
                    obj = getattr(module, attr)
                    if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                        plugin_instance = obj()
                        self.plugins.append(plugin_instance)
                        plugin_instance.on_load()
            except Exception as e:
                print(f"Failed to load plugin {module_name}: {e}")

    def unload_plugins(self):
        """Unload all loaded plugins."""
        for plugin in self.plugins:
            try:
                plugin.on_unload()
            except Exception as e:
                print(f"Failed to unload plugin {plugin.name}: {e}")
        self.plugins.clear()

# Global instance
plugin_manager = PluginManager()