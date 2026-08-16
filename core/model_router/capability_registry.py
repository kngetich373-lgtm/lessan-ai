"""Central source of truth for model capability metadata."""

from __future__ import annotations

import threading
from typing import Dict, Iterable, Optional, Tuple

from core.model_router.models import ModelCapabilities, ModelInfo


class ModelCapabilityRegistry:
    """Store normalized capabilities keyed by provider and model id.

    Provider adapters may advertise capabilities in their discovery payloads,
    but routing decisions read the normalized values from this registry. This
    prevents capability metadata from being duplicated across routing logic.
    """

    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], ModelCapabilities] = {}
        self._lock = threading.RLock()

    def register(self, provider: str, model: ModelInfo) -> None:
        caps = model.capabilities or ModelCapabilities()
        with self._lock:
            self._data[(provider.lower(), model.id)] = caps

    def register_many(self, provider: str, models: Iterable[ModelInfo]) -> None:
        for model in models:
            self.register(provider, model)

    def get(self, provider: str, model_id: str) -> Optional[ModelCapabilities]:
        with self._lock:
            return self._data.get((provider.lower(), model_id))

    def supports(self, provider: str, model_id: str, capability: str) -> bool:
        caps = self.get(provider, model_id)
        return caps.supports(capability) if caps else False

    def remove_provider(self, provider: str) -> None:
        prefix = provider.lower()
        with self._lock:
            for key in [key for key in self._data if key[0] == prefix]:
                self._data.pop(key, None)

    def snapshot(self) -> Dict[str, Dict[str, Dict]]:
        with self._lock:
            result: Dict[str, Dict[str, Dict]] = {}
            for (provider, model), caps in self._data.items():
                result.setdefault(provider, {})[model] = caps.as_dict()
            return result
