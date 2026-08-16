"""Provider Registry — thread-safe registration and lookup of AI providers."""

import threading
from typing import Dict, Iterable, List, Optional

from core.logging import get_logger
from core.model_router.base_provider import BaseModelProvider
from core.model_router.capabilities import ModelCapabilityRegistry
from core.model_router.models import ProviderHealth, ProviderInfo, ProviderStatus

logger = get_logger("ProviderRegistry")


class ProviderRegistry:
    """Thread-safe provider registry and owner of discovered model metadata."""

    def __init__(self, capability_registry: Optional[ModelCapabilityRegistry] = None) -> None:
        self._providers: Dict[str, BaseModelProvider] = {}
        self._infos: Dict[str, ProviderInfo] = {}
        self._health: Dict[str, ProviderHealth] = {}
        self._capabilities = capability_registry or ModelCapabilityRegistry()
        self._lock = threading.RLock()

    @property
    def capabilities(self) -> ModelCapabilityRegistry:
        """Authoritative model capability registry."""
        return self._capabilities

    def register(self, provider: BaseModelProvider) -> "ProviderRegistry":
        if not isinstance(provider, BaseModelProvider):
            raise ValueError(f"Provider must implement BaseModelProvider, got {type(provider).__name__}")
        name = provider.name
        if not name:
            raise ValueError("Provider name cannot be empty.")

        with self._lock:
            if name in self._providers:
                raise ValueError(f"Provider '{name}' is already registered.")
            info = provider.info()
            if info.name != name:
                info.name = name
            self._providers[name] = provider
            self._infos[name] = info
            self._health[name] = ProviderHealth(status=ProviderStatus.UNKNOWN)
            self._capabilities.register_provider(name, info.models)
            logger.info(f"Registered provider '{name}' ({len(info.models)} models, priority {info.priority})")
        return self

    def unregister(self, name: str) -> bool:
        with self._lock:
            existed = self._providers.pop(name, None) is not None
            self._infos.pop(name, None)
            self._health.pop(name, None)
            self._capabilities.remove_provider(name)
            if existed:
                logger.info(f"Unregistered provider '{name}'")
            return existed

    def clear(self) -> None:
        with self._lock:
            self._providers.clear()
            self._infos.clear()
            self._health.clear()
            self._capabilities.clear()

    def get(self, name: str) -> Optional[BaseModelProvider]:
        with self._lock:
            return self._providers.get(name)

    def get_info(self, name: str) -> Optional[ProviderInfo]:
        with self._lock:
            return self._infos.get(name)

    def get_health(self, name: str) -> ProviderHealth:
        with self._lock:
            return self._health.get(name, ProviderHealth())

    def set_health(self, name: str, health: ProviderHealth) -> None:
        with self._lock:
            if name in self._providers:
                self._health[name] = health

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._providers.keys())

    def all(self) -> List[BaseModelProvider]:
        with self._lock:
            return list(self._providers.values())

    def infos(self) -> List[ProviderInfo]:
        with self._lock:
            return list(self._infos.values())

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._providers

    def __len__(self) -> int:
        with self._lock:
            return len(self._providers)

    def by_local(self) -> List[BaseModelProvider]:
        return [p for p in self.all() if p.is_local]

    def by_remote(self) -> List[BaseModelProvider]:
        return [p for p in self.all() if not p.is_local]

    def with_capability(self, capability: str) -> List[BaseModelProvider]:
        names = set(self._capabilities.providers_for_capability(capability))
        return [p for p in self.all() if p.name in names]

    def ordered_by_priority(self, names: Optional[Iterable[str]] = None) -> List[BaseModelProvider]:
        with self._lock:
            wanted = set(names) if names is not None else None
            providers = [p for name, p in self._providers.items() if wanted is None or name in wanted]
            infos = dict(self._infos)
        return sorted(providers, key=lambda p: (infos.get(p.name, ProviderInfo(p.name)).priority, p.name))
