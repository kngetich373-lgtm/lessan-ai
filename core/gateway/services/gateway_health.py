"""Gateway Health Service — health checks for gateways and providers."""

import threading
import time
from typing import Callable, Dict, List, Optional

from core.gateway.hub import GatewayHub
from core.gateway.models import GatewayHealth, GatewayRecord, GatewayStatus
from core.logging import get_logger

logger = get_logger("GatewayHealthService")


class GatewayHealthService:
    """Periodically probes all connected gateways and updates their health."""

    def __init__(
        self,
        hub: GatewayHub,
        *,
        check_interval: float = 60.0,
        on_status_change: Optional[Callable[[GatewayHealth], None]] = None,
    ) -> None:
        self._hub = hub
        self._check_interval = max(5.0, float(check_interval))
        self._on_status_change = on_status_change
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "GatewayHealthService":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="gateway-health", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def check_all(self) -> List[GatewayHealth]:
        results = []
        for record in self._hub.health_all():
            health = GatewayHealth(
                gateway_id=record.config.gateway_id,
                status=record.status,
                last_error=record.last_error,
                consecutive_failures=record.consecutive_failures,
                consecutive_successes=record.consecutive_successes,
            )
            results.append(health)
            if self._on_status_change is not None:
                try:
                    self._on_status_change(health)
                except Exception:  # noqa: BLE001
                    pass
        return results

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_all()
            except Exception as exc:
                logger.error(f"Health round failed: {exc}")
            self._stop.wait(self._check_interval)
