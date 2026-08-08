"""Gateway Manager — connection lifecycle and automatic reconnection."""

import asyncio
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.gateway.adapters.base_adapter import BaseGatewayAdapter
from core.gateway.async_runner import BackgroundLoop, run_async
from core.gateway.exceptions import (
    AdapterNotFoundError,
    GatewayConnectionError,
    GatewayNotFoundError,
)
from core.gateway.models import GatewayConfig, GatewayRecord, GatewayStatus, GatewayType
from core.gateway.registry import GatewayRegistry
from core.logging import get_logger

logger = get_logger("GatewayManager")


class GatewayManager:
    """Manages the lifecycle of gateway connections.

    Responsibilities:
      - Connect / disconnect gateways
      - Automatic reconnection on failure
      - Background health probing
      - Adapter lookup by gateway type
    """

    def __init__(
        self,
        registry: GatewayRegistry,
        adapters: Dict[str, BaseGatewayAdapter],
        event_bus: Any = None,
        *,
        check_interval: float = 30.0,
        auto_reconnect: bool = True,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._registry = registry
        self._adapters = adapters
        self._event_bus = event_bus
        self._check_interval = max(1.0, float(check_interval))
        self._auto_reconnect = auto_reconnect
        self._reconnect_delay = max(0.5, float(reconnect_delay))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> "GatewayManager":
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="gateway-manager",
                daemon=True,
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    def connect(self, config: GatewayConfig) -> GatewayRecord:
        """Connect a gateway using the given configuration.

        Raises GatewayConnectionError if the connection fails.
        """
        adapter = self._get_adapter(config.gateway_type)
        existing = self._registry.get_gateway(config.gateway_id)
        if existing is not None and existing.is_connected:
            raise GatewayConnectionError(
                f"Gateway '{config.gateway_id}' is already connected."
            )

        self._publish("gateway.connecting", {"gateway_id": config.gateway_id})

        record = run_async(adapter.connect(config))

        if record.status == GatewayStatus.ERROR:
            self._publish("gateway.error", {"gateway_id": config.gateway_id, "error": record.last_error})
            raise GatewayConnectionError(
                f"Failed to connect gateway '{config.gateway_id}': {record.last_error}"
            )

        record.adapter = adapter
        self._registry.register_gateway(record)
        self._publish("gateway.connected", {"gateway_id": config.gateway_id})
        logger.info(f"Gateway '{config.gateway_id}' connected ({config.gateway_type}).")
        return record

    def disconnect(self, gateway_id: str) -> None:
        """Disconnect a gateway by ID."""
        record = self._registry.get_gateway(gateway_id)
        if record is None:
            raise GatewayNotFoundError(f"Gateway '{gateway_id}' not found.")

        if record.adapter is not None:
            run_async(record.adapter.disconnect(record))

        record.status = GatewayStatus.DISCONNECTED
        record.adapter = None
        self._registry.unregister_gateway(gateway_id)
        self._publish("gateway.disconnected", {"gateway_id": gateway_id})
        logger.info(f"Gateway '{gateway_id}' disconnected.")

    def enable(self, gateway_id: str) -> None:
        record = self._registry.get_gateway(gateway_id)
        if record is None:
            raise GatewayNotFoundError(f"Gateway '{gateway_id}' not found.")
        record.config.enabled = True
        self._publish("gateway.enabled", {"gateway_id": gateway_id})

    def disable(self, gateway_id: str) -> None:
        record = self._registry.get_gateway(gateway_id)
        if record is None:
            raise GatewayNotFoundError(f"Gateway '{gateway_id}' not found.")
        record.config.enabled = False
        self._publish("gateway.disabled", {"gateway_id": gateway_id})

    # ------------------------------------------------------------------ #
    # Adapter registry
    # ------------------------------------------------------------------ #
    def register_adapter(self, adapter: BaseGatewayAdapter) -> None:
        with self._lock:
            self._adapters[adapter.gateway_type] = adapter

    def get_adapter(self, gateway_type: str) -> Optional[BaseGatewayAdapter]:
        return self._adapters.get(gateway_type)

    # ------------------------------------------------------------------ #
    # Background loop
    # ------------------------------------------------------------------ #
    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._health_round()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Gateway manager round failed: {exc}")
            self._stop.wait(self._check_interval)

    def _health_round(self) -> None:
        for record in self._registry.gateways():
            if not record.config.enabled:
                continue
            if record.adapter is None:
                if self._auto_reconnect:
                    self._try_reconnect(record)
                continue
            try:
                updated = run_async(record.adapter.health(record))
                if updated.status == GatewayStatus.ERROR and self._auto_reconnect:
                    self._try_reconnect(record)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Health check failed for '{record.config.gateway_id}': {exc}")

    def _try_reconnect(self, record: GatewayRecord) -> None:
        logger.info(f"Attempting reconnect for '{record.config.gateway_id}'...")
        time.sleep(self._reconnect_delay)
        try:
            adapter = self._get_adapter(record.config.gateway_type)
            new_record = run_async(adapter.connect(record.config))
            if new_record.is_connected:
                new_record.adapter = adapter
                self._registry.register_gateway(new_record)
                self._publish("gateway.reconnected", {"gateway_id": record.config.gateway_id})
                logger.info(f"Gateway '{record.config.gateway_id}' reconnected.")
        except Exception as exc:
            logger.warning(f"Reconnect failed for '{record.config.gateway_id}': {exc}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_adapter(self, gateway_type) -> BaseGatewayAdapter:
        key = gateway_type.value if isinstance(gateway_type, GatewayType) else gateway_type
        adapter = self._adapters.get(key)
        if adapter is None:
            raise AdapterNotFoundError(
                f"No adapter registered for gateway type '{gateway_type}'."
            )
        return adapter

    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event, payload)
            except Exception:  # noqa: BLE001
                pass
