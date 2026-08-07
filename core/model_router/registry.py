"""Provider Registry — thread-safe registration and lookup of AI providers.

The registry is the router's contact book. Providers register themselves
(or are registered by configuration), and the registry exposes them for
routing, health monitoring and inspection. It knows nothing about any
specific vendor.
"""

import threading
from typing import Dict, Iterable, List, Optional

from core.logging import get_logger

from core.model_router.base_provider import BaseModelProvider
from core.model_router.models import (
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
)

logger = get_logger("ProviderRegistry")


class ProviderRegistry:
    """Stores providers keyed by name and serves router lookups.

    Supports:
      - registering provider adapters (instances) or config-driven specs
      - duplicate-name rejection
      - unregistering and clearing
      - querying by name, local/remote, and capability
    """

    def __init__(self) -> None:
        self._providers: Dict[str, BaseModelProvider] = {}
        self._infos: Dict[str, ProviderInfo] = {}
        self._health: Dict[str, ProviderHealth] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(self, provider: BaseModelProvider) -> "ProviderRegistry":
        """Register a provider adapter.

        Args:
            provider: An instance implementing :class:`BaseModelProvider`.

        Raises:
            ValueError: If a provider with the same name is already
                registered, or the provider does not implement the ABC.
        """
        if not isinstance(provider, BaseModelProvider):
            raise ValueError(
                f"Provider must implement BaseModelProvider, got {type(provider).__name__}"
            )

        name = provider.name
        if not name:
            raise ValueError("Provider name cannot be empty.")

        with self._lock:
            if name in self._providers:
                raise ValueError(f"Provider '{name}' is already registered.")

            info = provider.info()
            if info.name != name:
                info.name = name  # keep registry key authoritative

            self._providers[name] = provider
            self._infos[name] = info
            self._health[name] = ProviderHealth(status=ProviderStatus.UNKNOWN)
            logger.info(f"Registered provider '{name}' "
                        f"({len(info.models)} models, priority {info.priority})")
        return self

    def unregister(self, name: str) -> bool:
        """Remove a provider. Returns True if it was present."""
        with self._lock:
            existed = (
                self._providers.pop(name, None) is not None
                or self._infos.pop(name, None) is not None
            )
            self._health.pop(name, None)
            if existed:
                logger.info(f"Unregistered provider '{name}'")
            return existed

    def clear(self) -> None:
        """Remove all registered providers."""
        with self._lock:
            self._providers.clear()
            self._infos.clear()
            self._health.clear()

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #
    def get(self, name: str) -> Optional[BaseModelProvider]:
        """Return the provider adapter by name, or None."""
        with self._lock:
            return self._providers.get(name)

    def get_info(self, name: str) -> Optional[ProviderInfo]:
        """Return the cached :class:`ProviderInfo` for a provider."""
        with self._lock:
            return self._infos.get(name)

    def get_health(self, name: str) -> ProviderHealth:
        """Return the current health snapshot (defaults to UNKNOWN)."""
        with self._lock:
            return self._health.get(name, ProviderHealth())

    def set_health(self, name: str, health: ProviderHealth) -> None:
        """Update the cached health snapshot for a provider."""
        with self._lock:
            self._health[name] = health

    def names(self) -> List[str]:
        """Return all registered provider names, sorted."""
        with self._lock:
            return sorted(self._providers.keys())

    def all(self) -> List[BaseModelProvider]:
        """Return all registered provider adapters."""
        with self._lock:
            return list(self._providers.values())

    def infos(self) -> List[ProviderInfo]:
        """Return cached info for all registered providers."""
        with self._lock:
            return list(self._infos.values())

    def has(self, name: str) -> bool:
        """Return True if a provider is registered."""
        with self._lock:
            return name in self._providers

    def __len__(self) -> int:
        with self._lock:
            return len(self._providers)

    # ------------------------------------------------------------------ #
    # Filtered queries
    # ------------------------------------------------------------------ #
    def by_local(self) -> List[BaseModelProvider]:
        """Return providers that run locally (offline capable)."""
        return [p for p in self.all() if p.is_local]

    def by_remote(self) -> List[BaseModelProvider]:
        """Return providers that require network access."""
        return [p for p in self.all() if not p.is_local]

    def with_capability(self, capability: str) -> List[BaseModelProvider]:
        """Return providers advertising a given capability."""
        matches = []
        for provider in self.all():
            info = self.get_info(provider.name)
            if info is not None and info.primary_capabilities().supports(capability):
                matches.append(provider)
            elif provider.capabilities().get(capability, False):
                matches.append(provider)
        return matches

    # ------------------------------------------------------------------ #
    # Preference ordering
    # ------------------------------------------------------------------ #
    def ordered_by_priority(self, names: Optional[Iterable[str]] = None) -> List[BaseModelProvider]:
        """Return providers sorted by priority (lowest number first).

        Args:
            names: Optional subset of provider names to consider. When
                omitted, all registered providers are considered.
        """
        with self._lock:
            wanted = set(names) if names is not None else None
            providers = [
                p
                for name, p in self._providers.items()
                if wanted is None or name in wanted
            ]

        def _priority(provider: BaseModelProvider) -> int:
            info = self._infos.get(provider.name)
            return info.priority if info is not None else 100

        return sorted(providers, key=lambda p: (_priority(p), p.name))