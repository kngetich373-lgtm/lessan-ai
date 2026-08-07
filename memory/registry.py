"""MemoryRegistry — thread-safe registration and lookup of memory providers.

Mirrors :class:`core.model_router.registry.ProviderRegistry`. The registry
is the manager's contact book; it knows nothing about storage backends.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from core.logging import get_logger

from memory.events import (
    EV_PROVIDER_REGISTERED,
    EV_PROVIDER_UNREGISTERED,
    emit_memory_event,
)
from memory.provider import IMemoryProvider
from memory.scopes import MemoryScope

logger = get_logger("memory.registry")


class MemoryRegistry:
    """Stores :class:`IMemoryProvider` instances keyed by name."""

    def __init__(self, event_bus: object = None) -> None:
        self._providers: Dict[str, IMemoryProvider] = {}
        self._lock = threading.RLock()
        self._event_bus = event_bus

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(self, provider: IMemoryProvider) -> "MemoryRegistry":
        """Register a provider adapter.

        Raises:
            ValueError: If the provider is invalid or the name collides.
        """
        if not isinstance(provider, IMemoryProvider):
            raise ValueError(
                f"Provider must implement IMemoryProvider, got {type(provider).__name__}"
            )
        name = provider.name
        if not name:
            raise ValueError("Provider name cannot be empty.")

        with self._lock:
            if name in self._providers:
                raise ValueError(f"Memory provider '{name}' is already registered.")
            self._providers[name] = provider
            logger.info(
                f"Registered memory provider '{name}' "
                f"(scopes={[s.value for s in provider.supported_scopes()]})"
            )

        emit_memory_event(
            EV_PROVIDER_REGISTERED,
            {"provider": name, "scopes": [s.value for s in provider.supported_scopes()]},
            bus=self._event_bus,
        )
        return self

    def unregister(self, name: str) -> bool:
        """Remove a provider. Returns True if it was present."""
        with self._lock:
            existed = self._providers.pop(name, None) is not None
        if existed:
            logger.info(f"Unregistered memory provider '{name}'")
            emit_memory_event(
                EV_PROVIDER_UNREGISTERED,
                {"provider": name},
                bus=self._event_bus,
            )
        return existed

    def clear(self) -> None:
        """Remove all registered providers."""
        with self._lock:
            names = list(self._providers.keys())
            self._providers.clear()
        for name in names:
            emit_memory_event(
                EV_PROVIDER_UNREGISTERED,
                {"provider": name},
                bus=self._event_bus,
            )

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #
    def get(self, name: str) -> Optional[IMemoryProvider]:
        with self._lock:
            return self._providers.get(name)

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._providers

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._providers.keys())

    def all(self) -> List[IMemoryProvider]:
        with self._lock:
            return list(self._providers.values())

    def for_scope(self, scope: MemoryScope) -> List[IMemoryProvider]:
        """Return providers that support ``scope`` (registration order)."""
        return [p for p in self.all() if p.supports_scope(scope)]

    def primary_for_scope(self, scope: MemoryScope) -> Optional[IMemoryProvider]:
        """Return the first provider registered for ``scope``, if any."""
        providers = self.for_scope(scope)
        return providers[0] if providers else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._providers)
