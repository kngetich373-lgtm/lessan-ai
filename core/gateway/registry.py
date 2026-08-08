"""Gateway Registry — thread-safe registration and lookup of gateways and providers."""

import threading
from typing import Dict, List, Optional

from core.gateway.models import GatewayRecord, GatewayStatus, ProviderRecord
from core.logging import get_logger

logger = get_logger("GatewayRegistry")


class GatewayRegistry:
    """Stores gateway and provider records keyed by ID.

    The registry is the hub's contact book for gateways and the
    provider index for discovery results. It is thread-safe and
    supports querying by status, gateway, and capability.
    """

    def __init__(self) -> None:
        self._gateways: Dict[str, GatewayRecord] = {}
        self._providers: Dict[str, ProviderRecord] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Gateway registration
    # ------------------------------------------------------------------ #
    def register_gateway(self, record: GatewayRecord) -> "GatewayRegistry":
        with self._lock:
            self._gateways[record.config.gateway_id] = record
        logger.debug(f"Gateway registered: {record.config.gateway_id}")
        return self

    def unregister_gateway(self, gateway_id: str) -> Optional[GatewayRecord]:
        with self._lock:
            record = self._gateways.pop(gateway_id, None)
        if record is not None:
            self._remove_providers_for_gateway(gateway_id)
            logger.debug(f"Gateway unregistered: {gateway_id}")
        return record

    def get_gateway(self, gateway_id: str) -> Optional[GatewayRecord]:
        with self._lock:
            return self._gateways.get(gateway_id)

    def gateways(self) -> List[GatewayRecord]:
        with self._lock:
            return list(self._gateways.values())

    def connected_gateways(self) -> List[GatewayRecord]:
        with self._lock:
            return [r for r in self._gateways.values() if r.is_connected]

    def healthy_gateways(self) -> List[GatewayRecord]:
        with self._lock:
            return [r for r in self._gateways.values() if r.is_healthy]

    # ------------------------------------------------------------------ #
    # Provider registration
    # ------------------------------------------------------------------ #
    def register_provider(self, provider: ProviderRecord) -> "GatewayRegistry":
        with self._lock:
            self._providers[provider.provider_id] = provider
        return self

    def register_providers(self, providers: List[ProviderRecord]) -> "GatewayRegistry":
        for p in providers:
            self.register_provider(p)
        return self

    def unregister_provider(self, provider_id: str) -> Optional[ProviderRecord]:
        with self._lock:
            return self._providers.pop(provider_id, None)

    def get_provider(self, provider_id: str) -> Optional[ProviderRecord]:
        with self._lock:
            return self._providers.get(provider_id)

    def providers(self) -> List[ProviderRecord]:
        with self._lock:
            return list(self._providers.values())

    def providers_for_gateway(self, gateway_id: str) -> List[ProviderRecord]:
        with self._lock:
            return [p for p in self._providers.values() if p.gateway_id == gateway_id]

    def clear(self) -> None:
        with self._lock:
            self._gateways.clear()
            self._providers.clear()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _remove_providers_for_gateway(self, gateway_id: str) -> None:
        to_remove = [pid for pid, p in self._providers.items() if p.gateway_id == gateway_id]
        for pid in to_remove:
            del self._providers[pid]
