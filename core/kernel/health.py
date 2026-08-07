"""KernelHealthMonitor — periodic health probing of kernel components.

Runs a daemon thread that probes every monitorable component on a fixed
interval. Each probe records latency, consecutive success/failure counts and
a status (``HEALTHY`` / ``DEGRADED`` / ``UNHEALTHY``). Components whose
:meth:`~core.kernel.component.KernelComponent.health_check` returns ``None``
are treated as "not monitored" and are left untouched.
"""

import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from core.logging import get_logger

from core.kernel.component import KernelComponent
from core.kernel.models import ComponentHealth, ComponentStatus

logger = get_logger("KernelHealthMonitor")


class KernelHealthMonitor:
    """Background health monitor for kernel components.

    Args:
        components: Mapping of component name → KernelComponent.
        health_state: Mapping of component name → ComponentHealth.
        on_status_change: Optional callback ``(name, health)`` invoked on
            status transitions (e.g. RUNNING → UNHEALTHY).
        check_interval: Seconds between probe rounds.
        timeout: Per-probe budget in seconds; probes slower than this mark
            the component ``DEGRADED`` even when they succeed.
    """

    def __init__(
        self,
        components: Dict[str, KernelComponent],
        health_state: Dict[str, ComponentHealth],
        on_status_change: Optional[Callable[[str, ComponentHealth], None]] = None,
        *,
        check_interval: float = 5.0,
        timeout: float = 5.0,
    ) -> None:
        self._components = components
        self._health_state = health_state
        self._on_status_change = on_status_change
        self._check_interval = float(check_interval)
        self._timeout = float(timeout)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "KernelHealthMonitor":
        """Start the monitoring thread."""
        if self.running:
            return self
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="kernel-health-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Kernel health monitor started")
        return self

    def stop(self) -> None:
        """Stop the monitoring thread and wait for it to exit."""
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    # ------------------------------------------------------------------ #
    # Probing
    # ------------------------------------------------------------------ #
    def check(self, name: str) -> Optional[ComponentHealth]:
        """Probe a single component. Returns the new health record or None
        when the component does not support monitoring."""
        component = self._components.get(name)
        if component is None:
            return None

        current = self._health_state.get(name)
        if current is not None and current.status not in (
            ComponentStatus.RUNNING,
            ComponentStatus.HEALTHY,
            ComponentStatus.DEGRADED,
            ComponentStatus.UNHEALTHY,
        ):
            # Only probe components that have actually started: a component
            # whose start() failed (FAILED) or that was stopped must not be
            # flipped to HEALTHY by a live probe.
            return None

        started = time.monotonic()
        ok: Optional[bool] = None
        error: Optional[str] = None
        try:
            ok = component.health_check()
        except Exception as exc:  # noqa: BLE001 - probes must never crash
            ok = False
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = (time.monotonic() - started) * 1000.0

        if ok is None:
            # Not monitorable — leave the record untouched.
            return None

        previous = self._health_state.get(
            name, ComponentHealth(status=ComponentStatus.REGISTERED)
        )
        now = datetime.now()

        if ok:
            status = (
                ComponentStatus.DEGRADED
                if latency_ms > self._timeout * 1000.0
                else ComponentStatus.HEALTHY
            )
            health = ComponentHealth(
                status=status,
                latency_ms=latency_ms,
                last_checked=now,
                error=None,
                consecutive_failures=0,
                consecutive_successes=previous.consecutive_successes + 1,
            )
        else:
            health = ComponentHealth(
                status=ComponentStatus.UNHEALTHY,
                latency_ms=latency_ms,
                last_checked=now,
                error=error or "health check returned False",
                consecutive_failures=previous.consecutive_failures + 1,
                consecutive_successes=0,
            )

        self._health_state[name] = health
        if self._on_status_change is not None and health.status != previous.status:
            try:
                self._on_status_change(name, health)
            except Exception:  # noqa: BLE001 - keep the monitor alive
                logger.warning(f"on_status_change handler failed for '{name}'")
        return health

    def check_all(self) -> Dict[str, ComponentHealth]:
        """Probe every monitorable component in one round."""
        results: Dict[str, ComponentHealth] = {}
        for name in list(self._components):
            health = self.check(name)
            if health is not None:
                results[name] = health
        return results

    def healthy_components(self) -> List[str]:
        return [
            name
            for name, health in self._health_state.items()
            if health.is_healthy
        ]

    def unhealthy_components(self) -> List[str]:
        return [
            name
            for name, health in self._health_state.items()
            if health.status == ComponentStatus.UNHEALTHY
        ]

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_all()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Kernel health round failed: {exc}")
            self._stop.wait(self._check_interval)
