"""Global application state management for Lessan AI."""

import threading
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional


class StateStore:
    """A thread-safe, observable global state store.

    State is stored under named slices. Listeners can subscribe to specific
    slices or to every state change. The store emits change notifications
    after each mutation, including a deep copy of the changed slice.
    """

    def __init__(self) -> None:
        self._state: Dict[str, Any] = {}
        self._listeners: Dict[str, List[Callable[[str, Any], None]]] = {}
        self._global_listeners: List[Callable[[str, Any], None]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, slice_name: str, default: Any = None) -> Any:
        """Get a deep copy of a state slice."""
        with self._lock:
            return deepcopy(self._state.get(slice_name, default))

    def get_state(self) -> Dict[str, Any]:
        """Get a deep copy of the entire state."""
        with self._lock:
            return deepcopy(self._state)

    def has(self, slice_name: str) -> bool:
        with self._lock:
            return slice_name in self._state

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def set(self, slice_name: str, value: Any) -> None:
        """Replace an entire state slice and notify listeners."""
        with self._lock:
            self._state[slice_name] = deepcopy(value)
        self._notify(slice_name, value)

    def update(self, slice_name: str, patch: Dict[str, Any]) -> None:
        """Merge a dict patch into an existing slice (or create it)."""
        with self._lock:
            current = self._state.get(slice_name, {})
            if isinstance(current, dict) and isinstance(patch, dict):
                current.update(deepcopy(patch))
            else:
                current = deepcopy(patch)
            self._state[slice_name] = current
        self._notify(slice_name, current)

    def update_state(self, slice_name: str, data: Any) -> None:
        """Backwards-compatible alias for :meth:`update`."""
        self.update(slice_name, data)

    def delete(self, slice_name: str) -> bool:
        """Remove a slice. Returns True if it existed."""
        with self._lock:
            existed = slice_name in self._state
            if existed:
                del self._state[slice_name]
        if existed:
            self._notify(slice_name, None)
        return existed

    # ------------------------------------------------------------------ #
    # Subscriptions
    # ------------------------------------------------------------------ #
    def subscribe(
        self, slice_name: str, listener: Callable[[str, Any], None]
    ) -> Callable[[str, Any], None]:
        """Subscribe to changes on a specific slice.

        The listener receives ``(slice_name, value)``. Returns the listener
        so it can be passed to :meth:`unsubscribe`.
        """
        with self._lock:
            self._listeners.setdefault(slice_name, []).append(listener)
        return listener

    def subscribe_all(self, listener: Callable[[str, Any], None]) -> Callable[[str, Any], None]:
        """Subscribe to every state change."""
        with self._lock:
            self._global_listeners.append(listener)
        return listener

    def unsubscribe(self, slice_name: str, listener: Callable[[str, Any], None]) -> bool:
        with self._lock:
            listeners = self._listeners.get(slice_name)
            if listeners and listener in listeners:
                listeners.remove(listener)
                return True
        # fall back to global listeners
        with self._lock:
            if listener in self._global_listeners:
                self._global_listeners.remove(listener)
                return True
        return False

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _notify(self, slice_name: str, value: Any) -> None:
        with self._lock:
            slice_listeners = list(self._listeners.get(slice_name, ()))
            global_listeners = list(self._global_listeners)
        for listener in slice_listeners:
            try:
                listener(slice_name, deepcopy(value))
            except Exception:  # noqa: BLE001 - keep store resilient
                pass
        for listener in global_listeners:
            try:
                listener(slice_name, deepcopy(value))
            except Exception:  # noqa: BLE001
                pass


# Global state instance
state = StateStore()