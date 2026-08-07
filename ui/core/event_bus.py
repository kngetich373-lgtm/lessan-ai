from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    """Centralized event bus for decoupled communication."""
    agent_state_changed = pyqtSignal(dict)
    workspace_switched = pyqtSignal(str)
    plugin_loaded = pyqtSignal(str)
    metric_updated = pyqtSignal(dict)
    chat_message = pyqtSignal(str)
    file_dropped = pyqtSignal(str)

# Global instance
bus = EventBus()