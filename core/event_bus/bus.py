"""Event-driven communication bus for Lessan AI."""

import inspect
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional


class EventBus:
    """A thread-safe, synchronous pub/sub event bus.

    Subscribers register a callback for a named event topic. When ``emit``
    is called, each callback receives the event payload (a ``dict``) and the
    event name. Callbacks that accept two positional parameters receive
    ``(event_name, payload)``; single-parameter callbacks receive the payload.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[..., Any]]] = defaultdict(list)
        self._lock = threading.RLock()
        self._once: Dict[str, List[Callable[..., Any]]] = defaultdict(list)

    # ------------------------------------------------------------------ #
    # Subscription
    # ------------------------------------------------------------------ #
    def subscribe(self, event: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Register a handler for an event.

        Returns the handler so it can be used with :meth:`unsubscribe`.
        """
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self._lock:
            self._subscribers[event].append(handler)
        return handler

    def subscribe_once(self, event: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Register a handler that fires at most once for a given event."""
        with self._lock:
            self._once[event].append(handler)
        return handler

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> bool:
        """Remove a previously registered handler. Returns True if removed."""
        with self._lock:
            try:
                self._subscribers[event].remove(handler)
                return True
            except ValueError:
                try:
                    self._once[event].remove(handler)
                    return True
                except ValueError:
                    return False

    def on(self, event: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Alias for :meth:`subscribe`."""
        return self.subscribe(event, handler)

    def off(self, event: str, handler: Callable[..., Any]) -> bool:
        """Alias for :meth:`unsubscribe`."""
        return self.unsubscribe(event, handler)

    # ------------------------------------------------------------------ #
    # Emission
    # ------------------------------------------------------------------ #
    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Publish an event to all subscribed handlers.

        A handler is invoked with the payload alone if it declares a single
        positional parameter; otherwise it receives ``(event, payload)``.
        """
        payload = payload or {}
        with self._lock:
            handlers = list(self._subscribers.get(event, ()))
            once = list(self._once.get(event, ()))

        errors: List[Exception] = []
        for handler in handlers:
            try:
                self._invoke(handler, event, payload)
            except Exception as exc:  # noqa: BLE001 - keep bus resilient
                errors.append(exc)

        if once:
            with self._lock:
                # Remove the handlers that were fired this round
                remaining = [h for h in self._once.get(event, ()) if h not in once]
                self._once[event] = remaining
            for handler in once:
                try:
                    self._invoke(handler, event, payload)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        if errors:
            # Re-raise the first error after delivering to everyone else
            raise errors[0]

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def subscribers_for(self, event: str) -> List[Callable[..., Any]]:
        """Return the currently registered handlers for an event."""
        with self._lock:
            return list(self._subscribers.get(event, ())) + list(self._once.get(event, ()))

    def events(self) -> List[str]:
        """Return all event names that have at least one subscriber."""
        with self._lock:
            return sorted(set(self._subscribers) | set(self._once))

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._subscribers.clear()
            self._once.clear()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _invoke(handler: Callable[..., Any], event: str, payload: Dict[str, Any]) -> None:
        try:
            sig = inspect.signature(handler)
        except (TypeError, ValueError):
            handler(payload)
            return

        params = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
            and p.name != "self"
        ]
        if len(params) == 1:
            handler(payload)
        elif len(params) >= 2:
            handler(event, payload)
        else:
            handler()


# Global event bus instance
event_bus = EventBus()

# Alias for convenience
bus = event_bus