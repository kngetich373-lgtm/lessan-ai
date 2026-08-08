"""Gateway Discovery Service — periodic provider discovery from connected gateways."""

import threading
import time
from typing import Callable, Dict, List, Optional

from core.gateway.hub import GatewayHub
from core.gateway.models import ProviderRecord
from core.logging import get_logger

logger = get_logger("GatewayDiscoveryService")


class GatewayDiscoveryService:
    """Periodically refreshes provider discovery from all connected gateways."""

    def __init__(
        self,
        hub: GatewayHub,
        *,
        interval: float = 300.0,
        on_discovery: Optional[Callable[[List[ProviderRecord]], None]] = None,
    ) -> None:
        self._hub = hub
        self._interval = max(10.0, float(interval))
        self._on_discovery = on_discovery
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "GatewayDiscoveryService":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="gateway-discovery", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def refresh(self) -> List[ProviderRecord]:
        providers = self._hub.discover_all()
        if self._on_discovery is not None:
            self._on_discovery(providers)
        return providers

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception as exc:
                logger.error(f"Discovery round failed: {exc}")
            self._stop.wait(self._interval)
