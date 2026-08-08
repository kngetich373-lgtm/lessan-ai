"""Gateway Hub — the single entry point for the Routing Engine.

The Gateway Hub owns all gateway adapters, connections, providers, and
metrics. The Routing Engine talks ONLY to the Gateway Hub and never knows
about individual gateways, adapters, or providers.
"""

import asyncio
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.gateway.async_runner import run_async
from core.gateway.exceptions import (
    GatewayNotFoundError,
    ModelNotFoundError,
    ProviderNotFoundError,
)
from core.gateway.manager import GatewayManager
from core.gateway.models import (
    GatewayCapabilities,
    GatewayConfig,
    GatewayMetrics,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    ModelRecord,
    ProviderRecord,
)
from core.gateway.registry import GatewayRegistry
from core.logging import get_logger

logger = get_logger("GatewayHub")


class GatewayHub:
    """Central facade for all gateway operations.

    The Routing Engine must use this class exclusively. It knows nothing
    about individual gateway APIs — every call goes through the hub.
    """

    def __init__(
        self,
        registry: Optional[GatewayRegistry] = None,
        manager: Optional[GatewayManager] = None,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry or GatewayRegistry()
        self._manager = manager or GatewayManager(
            registry=self._registry,
            adapters={},
            event_bus=event_bus,
        )
        self._event_bus = event_bus

    # ------------------------------------------------------------------ #
    # Gateway lifecycle
    # ------------------------------------------------------------------ #
    def connect(self, config: GatewayConfig) -> GatewayRecord:
        """Connect a gateway and start discovering providers."""
        record = self._manager.connect(config)
        if record.is_connected:
            try:
                adapter = record.adapter
                providers = run_async(adapter.discover(record))
                self._registry.register_providers(providers)
                for p in providers:
                    self._publish("gateway.provider_discovered", {"provider": p.as_dict()})
            except Exception as exc:
                logger.warning(f"Discovery failed for '{config.gateway_id}': {exc}")
        return record

    def disconnect(self, gateway_id: str) -> None:
        self._manager.disconnect(gateway_id)

    def enable(self, gateway_id: str) -> None:
        self._manager.enable(gateway_id)

    def disable(self, gateway_id: str) -> None:
        self._manager.disable(gateway_id)

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    def health(self, gateway_id: str) -> Optional[GatewayRecord]:
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
            return record
        return run_async(record.adapter.health(record))

    def health_all(self) -> List[GatewayRecord]:
        results = []
        for record in self._registry.gateways():
            if record.adapter is not None:
                results.append(run_async(record.adapter.health(record)))
        return results

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    def discover(self, gateway_id: str) -> List[ProviderRecord]:
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
            return []
        providers = run_async(record.adapter.discover(record))
        self._registry.register_providers(providers)
        return providers

    def discover_all(self) -> List[ProviderRecord]:
        all_providers: List[ProviderRecord] = []
        for record in self._registry.connected_gateways():
            if record.adapter is not None:
                providers = run_async(record.adapter.discover(record))
                self._registry.register_providers(providers)
                all_providers.extend(providers)
        return all_providers

    # ------------------------------------------------------------------ #
    # Provider registry
    # ------------------------------------------------------------------ #
    def list_providers(self) -> List[ProviderRecord]:
        return self._registry.providers()

    def get_provider(self, provider_id: str) -> Optional[ProviderRecord]:
        return self._registry.get_provider(provider_id)

    def provider_details(self, provider_id: str) -> Optional[ProviderRecord]:
        provider = self._registry.get_provider(provider_id)
        if provider is None:
            return None
        record = self._registry.get_gateway(provider.gateway_id)
        if record is None or record.adapter is None:
            return provider
        return run_async(record.adapter.provider_details(record, provider_id))

    # ------------------------------------------------------------------ #
    # Invocation — the only entry point the Routing Engine uses
    # ------------------------------------------------------------------ #
    def chat(self, request: GatewayRequest) -> GatewayResponse:
        """Execute a chat request through the appropriate gateway.

        The Routing Engine calls this method exclusively. It never knows
        which gateway or provider handled the request.
        """
        gateway_id = self._resolve_gateway(request)
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
            return GatewayResponse(
                text="",
                error=f"Gateway '{gateway_id}' not available.",
                success=False,
            )
        response = run_async(record.adapter.chat(record, request))
        self._publish("gateway.response", {"gateway_id": gateway_id, "success": response.success})
        return response

    def stream_chat(self, request: GatewayRequest):
        """Execute a streaming chat request.

        Yields GatewayResponse chunks.
        """
        gateway_id = self._resolve_gateway(request)
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
                 raise GatewayNotFoundError(f"Gateway '{gateway_id}' not available.")

        async def _stream():
            async for chunk in record.adapter.stream_chat(record, request):
                yield chunk

        return _stream()

    def embeddings(self, texts: List[str], model: Optional[str] = None, gateway: Optional[str] = None) -> List[List[float]]:
        gateway_id = gateway or self._default_gateway_id()
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
            raise GatewayNotFoundError(f"Gateway '{gateway_id}' not available.")
        return run_async(record.adapter.embeddings(record, texts, model))

    def image_generation(self, prompt: str, model: Optional[str] = None, gateway: Optional[str] = None, **kwargs: Any) -> bytes:
        gateway_id = gateway or self._default_gateway_id()
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
            raise GatewayNotFoundError(f"Gateway '{gateway_id}' not available.")
        return run_async(record.adapter.image_generation(record, prompt, model, **kwargs))

    def speech(self, text: str, model: Optional[str] = None, gateway: Optional[str] = None, **kwargs: Any) -> bytes:
        gateway_id = gateway or self._default_gateway_id()
        record = self._registry.get_gateway(gateway_id)
        if record is None or record.adapter is None:
            raise GatewayNotFoundError(f"Gateway '{gateway_id}' not available.")
        return run_async(record.adapter.speech(record, text, model, **kwargs))

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #
    def metrics(self, gateway_id: Optional[str] = None) -> List[GatewayMetrics]:
        results = []
        for record in self._registry.gateways():
            if gateway_id and record.config.gateway_id != gateway_id:
                continue
            if record.adapter is not None:
                metrics = record.adapter._metrics_for(record.config.gateway_id)
                results.append(metrics)
        return results

    # ------------------------------------------------------------------ #
    # Adapter registration
    # ------------------------------------------------------------------ #
    def register_adapter(self, adapter: Any) -> None:
        self._manager.register_adapter(adapter)

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #
    @property
    def connected_gateways(self) -> List[GatewayRecord]:
        return self._registry.connected_gateways()

    @property
    def providers(self) -> List[ProviderRecord]:
        return self._registry.providers()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_gateway(self, request: GatewayRequest) -> str:
        if request.gateway:
            return request.gateway
        if request.provider:
            provider = self._registry.get_provider(request.provider)
            if provider is not None:
                return provider.gateway_id
        return self._default_gateway_id()

    def _default_gateway_id(self) -> str:
        connected = self._registry.connected_gateways()
        if not connected:
            raise GatewayNotFoundError("No gateways are connected.")
        connected.sort(key=lambda r: r.config.priority)
        return connected[0].config.gateway_id

    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event, payload)
            except Exception:  # noqa: BLE001
                pass


def _get_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            return loop
    except RuntimeError:
        pass
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop
