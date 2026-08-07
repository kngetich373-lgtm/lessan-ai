from PyQt6.QtCore import QObject, pyqtSignal

class StateManager(QObject):
    """Centralized state management for Lessan AI."""
    state_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._state = {
            "workspace": "Astral Realm",
            "agents": [],
            "active_agent": None,
            "plugins": [],
            "metrics": {
                "cpu": 0.0,
                "mem": 0.0,
                "net": 0.0,
                "gpu": -1.0,
                "tmp": -1.0,
                "bat": -1.0,
                "charging": False
            },
            "ui": {
                "theme": "Galaxy Diamond Nebula",
                "panels": {}
            }
        }

    def get_state(self):
        return self._state

    def update_state(self, slice_name, data):
        if slice_name in self._state:
            if isinstance(self._state[slice_name], dict) and isinstance(data, dict):
                self._state[slice_name].update(data)
            else:
                self._state[slice_name] = data
            self.state_changed.emit(self._state)

# Global instance
state = StateManager()