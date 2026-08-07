"""Provider Health Monitor — periodic health checks for registered providers.

The monitor pings each provider on a configurable interval, records latency
and success/failure history, and exposes the results to the routing and
fallback logic. It is provider-agnostic: it only calls
``provider.check_health()``.
"""

import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from core.logging import get_logger

from core.model_router.models import ProviderHealth, ProviderStatus
from core.model_router.registry import ProviderRegistry

logger = get_logger("ProviderHealthMonitor")


class ProviderHealthMonitor:
    """Periodically probes all registered providers.

    Args:
        registry: The provider registry to monitor.
        check_interval: Seconds between health-check rounds.
        timeout: Per-provider timeout in seconds.
        on_status_change: Optional callback ``(provider_name, health)``
            invoked whenever a provider's status transitions.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        check_interval: float = 60.0,
        timeout: float = 5.0,
        on_status_change: Optional[Callable[[str, ProviderHealth], None]] = None,
    ) -> None:
        self._registry = registry
        self._check_interval = max(1.0, float(check_interval))
        self._timeout = max(0.1, float(timeout))
        self._on_status_change = on_status_change

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()  # guards manual + thread updates

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> "ProviderHealthMonitor":
        """Start the background monitoring thread (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="provider-health-monitor",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                f"Health monitor started (interval={self._check_interval}s, "
                f"timeout={self._timeout}s)"
            )
        return self

    def stop(self) -> None:
        """Stop the background monitoring thread."""
        self._stop.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self._check_interval + 1.0))

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # Probing
    # ------------------------------------------------------------------ #
    def check_all(self) -> Dict[str, ProviderHealth]:
        """Run one probe round against every registered provider.

        Returns a snapshot of the resulting health states keyed by name.
        """
        results: Dict[str, ProviderHealth] = {}
        for name in self._registry.names():
            results[name] = self.check(name)
        return results

    def check(self, name: str) -> ProviderHealth:
        """Probe a single provider and update its cached health.

        Uses ``check_health()`` from the provider adapter. If the provider
        is missing from the registry, an UNHEALTHY snapshot is returned.
        """
        provider = self._registry.get(name)
        if provider is None:
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, error="not registered")

        start = time.monotonic()
        ok = False
        error: Optional[str] = None
        try:
            ok = bool(provider.check_health())
        except Exception as exc:  # noqa: BLE001 - keep monitor resilient
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"Health check failed for '{name}': {error}")
        latency_ms = (time.monotonic() - start) * 1000.0

        previous = self._registry.get_health(name)
        if ok:
            status = (
                ProviderStatus.DEGRADED
                if latency_ms > self._timeout * 1000.0
                else ProviderStatus.HEALTHY
            )
            health = ProviderHealth(
                status=status,
                latency_ms=latency_ms,
                last_checked=datetime.now(),
                error=None,
                consecutive_failures=0,
                consecutive_successes=previous.consecutive_successes + 1,
            )
        else:
            health = ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                latency_ms=latency_ms,
                last_checked=datetime.now(),
                error=error or "health check returned False",
                consecutive_failures=previous.consecutive_failures + 1,
                consecutive_successes=0,
            )

        self._registry.set_health(name, health)
        if self._on_status_change is not None and health.status != previous.status:
            try:
                self._on_status_change(name, health)
            except Exception:  # noqa: BLE001
                pass

        return health

    # ------------------------------------------------------------------ #
    # Status access
    # ------------------------------------------------------------------ #
    def status(self, name: str) -> ProviderHealth:
        """Return the current cached health snapshot for a provider."""
        return self._registry.get_health(name)

    def healthy_providers(self) -> List[str]:
        """Return names of providers currently considered healthy."""
        return [
            name
            for name in self._registry.names()
            if self._registry.get_health(name).is_healthy
        ]

    def unhealthy_providers(self) -> List[str]:
        """Return names of providers currently considered unhealthy."""
        return [
            name
            for name in self._registry.names()
            if not self._registry.get_health(name).is_healthy
        ]

    def snapshot(self) -> Dict[str, Dict]:
        """Return a JSON-serializable health snapshot for all providers."""
        return {
            name: self._registry.get_health(name).as_dict()
            for name in self._registry.names()
        }

    # ------------------------------------------------------------------ #
    # Background loop
    # ------------------------------------------------------------------ #
    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_all()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Health monitor round failed: {exc}")
            self._stop.wait(self._check_interval)