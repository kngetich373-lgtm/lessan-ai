"""Resilient provider health monitoring for Lessan AI."""

import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from core.logging import get_logger
from core.model_router.models import ProviderHealth, ProviderStatus
from core.model_router.registry import ProviderRegistry

logger = get_logger("ProviderHealthMonitor")


class ProviderHealthMonitor:
    """Periodically probes providers without allowing one to block the monitor.

    Health checks are isolated from the monitoring loop. A slow provider is
    marked DEGRADED/UNHEALTHY after the configured timeout and cannot prevent
    other providers from being checked or Lessan from shutting down.
    """

    def __init__(self, registry: ProviderRegistry, check_interval: float = 60.0,
                 timeout: float = 5.0,
                 on_status_change: Optional[Callable[[str, ProviderHealth], None]] = None) -> None:
        self._registry = registry
        self._check_interval = max(1.0, float(check_interval))
        self._timeout = max(0.1, float(timeout))
        self._on_status_change = on_status_change
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._probe_threads: Dict[str, threading.Thread] = {}

    def start(self) -> "ProviderHealthMonitor":
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_loop, name="provider-health-monitor", daemon=True)
            self._thread.start()
            logger.info(f"Health monitor started (interval={self._check_interval}s, timeout={self._timeout}s)")
        return self

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, min(self._check_interval + 1.0, self._timeout + 2.0)))

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def check_all(self) -> Dict[str, ProviderHealth]:
        results: Dict[str, ProviderHealth] = {}
        for name in self._registry.names():
            if self._stop.is_set():
                break
            results[name] = self.check(name)
        return results

    def check(self, name: str) -> ProviderHealth:
        provider = self._registry.get(name)
        if provider is None:
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, error="not registered")

        with self._lock:
            existing_probe = self._probe_threads.get(name)
            if existing_probe is not None and existing_probe.is_alive():
                return self._registry.get_health(name)

        done = threading.Event()
        result = {"ok": False, "error": None}
        started = time.monotonic()

        def probe() -> None:
            try:
                result["ok"] = bool(provider.check_health())
            except Exception as exc:  # noqa: BLE001
                result["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                done.set()

        thread = threading.Thread(target=probe, name=f"provider-health:{name}", daemon=True)
        with self._lock:
            self._probe_threads[name] = thread
        thread.start()

        completed = done.wait(self._timeout)
        latency_ms = (time.monotonic() - started) * 1000.0
        with self._lock:
            if not thread.is_alive():
                self._probe_threads.pop(name, None)

        previous = self._registry.get_health(name)
        if not completed:
            error = f"health check timed out after {self._timeout:.1f}s"
            logger.warning(f"Health check timed out for '{name}'")
            health = ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                latency_ms=latency_ms,
                last_checked=datetime.now(),
                error=error,
                consecutive_failures=previous.consecutive_failures + 1,
                consecutive_successes=0,
            )
        elif result["ok"]:
            status = ProviderStatus.DEGRADED if latency_ms > self._timeout * 1000.0 else ProviderStatus.HEALTHY
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
                error=result["error"] or "health check returned False",
                consecutive_failures=previous.consecutive_failures + 1,
                consecutive_successes=0,
            )

        self._registry.set_health(name, health)
        if self._on_status_change is not None and health.status != previous.status:
            try:
                self._on_status_change(name, health)
            except Exception:  # noqa: BLE001
                logger.debug(f"Health status callback failed for '{name}'", exc_info=True)
        return health

    def status(self, name: str) -> ProviderHealth:
        return self._registry.get_health(name)

    def healthy_providers(self) -> List[str]:
        return [name for name in self._registry.names() if self._registry.get_health(name).is_healthy]

    def unhealthy_providers(self) -> List[str]:
        return [name for name in self._registry.names() if not self._registry.get_health(name).is_healthy]

    def snapshot(self) -> Dict[str, Dict]:
        return {name: self._registry.get_health(name).as_dict() for name in self._registry.names()}

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_all()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Health monitor round failed: {exc}")
            self._stop.wait(self._check_interval)
