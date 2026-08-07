from abc import ABC, abstractmethod

class PluginBase(ABC):
    """Base class for all Lessan AI plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @abstractmethod
    def on_load(self):
        """Called when the plugin is loaded."""
        pass

    @abstractmethod
    def on_unload(self):
        """Called when the plugin is unloaded."""
        pass

    def on_event(self, event_type: str, data: dict):
        """Called when an event is emitted on the event bus."""
        pass