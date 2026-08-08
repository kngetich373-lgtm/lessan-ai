"""Provider Registry Service — merged provider registry across all gateways."""

from typing import Dict, List, Optional

from core.gateway.models import ModelRecord, ProviderRecord
from core.gateway.registry import GatewayRegistry
from core.logging import get_logger

logger = get_logger("ProviderRegistryService")


class ProviderRegistryService:
    """High-level provider registry that aggregates providers from every
    connected gateway and exposes search/lookup helpers."""

    def __init__(self, registry: GatewayRegistry) -> None:
        self._registry = registry

    def all_providers(self) -> List[ProviderRecord]:
        return self._registry.providers()

    def all_models(self) -> List[ModelRecord]:
        models = []
        for p in self._registry.providers():
            models.extend(p.models)
        return models

    def find_provider(self, name: str) -> Optional[ProviderRecord]:
        for p in self._registry.providers():
            if p.name.lower() == name.lower() or p.provider_id.lower() == name.lower():
                return p
        return None

    def find_model(self, model_id: str) -> Optional[ModelRecord]:
        for p in self._registry.providers():
            for m in p.models:
                if m.model_id.lower() == model_id.lower():
                    return m
        return None

    def providers_by_capability(self, capability: str) -> List[ProviderRecord]:
        result = []
        for p in self._registry.providers():
            if p.capabilities.supports(capability):
                result.append(p)
        return result

    def models_by_capability(self, capability: str) -> List[ModelRecord]:
        result = []
        for p in self._registry.providers():
            for m in p.models:
                if m.capabilities.supports(capability):
                    result.append(m)
        return result

    def provider_count(self) -> int:
        return len(self._registry.providers())

    def model_count(self) -> int:
        return sum(len(p.models) for p in self._registry.providers())
