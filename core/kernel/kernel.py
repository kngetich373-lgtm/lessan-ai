"""AgentKernel — lifecycle management, dependency resolution and health
monitoring for the Lessan AI runtime.

The kernel is the composition root of the application. Subsystems implement
:class:`~core.kernel.component.KernelComponent` and register themselves with
an :class:`AgentKernel` instance, which then:

* resolves the component dependency graph into a deterministic start order,
* starts every component in dependency order (aborting the boot when a
  *critical* component fails, and rolling back the components already
  started),
* monitors component health on a background daemon thread and publishes
  status transitions on the event bus,
* shuts everything down gracefully in reverse dependency order.

Every lifecycle transition is published on the event bus and mirrored into
the state store (``kernel.status`` and ``kernel.components`` slices).
"""

import heapq
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.di.container import CircularDependencyError
from core.event_bus import event_bus as default_event_bus
from core.logging import get_logger
from core.state import state as default_state_store

from core.kernel.component import KernelComponent
from core.kernel.health import KernelHealthMonitor
from core.kernel.models import (
    ComponentHealth,
    ComponentStartRecord,
    ComponentStatus,
    KernelReport,
    KernelStatus,
)

logger = get_logger("AgentKernel")

# --------------------------------------------------------------------------- #
# Lifecycle events published on the kernel's event bus
# --------------------------------------------------------------------------- #
EV_KERNEL_BOOTING = "kernel.booting"
EV_KERNEL_STARTING = "kernel.starting"
EV_KERNEL_COMPONENT_STARTED = "kernel.component_started"
EV_KERNEL_COMPONENT_FAILED = "kernel.component_failed"
EV_KERNEL_RUNNING = "kernel.running"
EV_KERNEL_STOPPING = "kernel.stopping"
EV_KERNEL_COMPONENT_STOPPED = "kernel.component_stopped"
EV_KERNEL_STOPPED = "kernel.stopped"
EV_KERNEL_START_FAILED = "kernel.start_failed"
EV_KERNEL_HEALTH_CHANGED = "kernel.health_changed"


class KernelError(RuntimeError):
    """Base error for all AgentKernel failures."""


class KernelStartupError(KernelError):
    """Raised when a critical component fails to start and aborts the boot."""


class UnknownDependencyError(KernelError):
    """Raised when a component declares a dependency that was never registered."""


class AgentKernel:
    """Central runtime coordinator: lifecycle + dependency resolution + health.

    Args:
        container: Optional DI container. When provided it is wired into
            every component via :meth:`KernelComponent.wire` and the kernel
            itself is usable from the container.
        event_bus: Event bus to publish lifecycle events on. Defaults to the
            global ``core.event_bus.event_bus``.
        state_store: State store to mirror kernel state into. Defaults to the
            global ``core.state.state``.
        config: Optional configuration manager passed to standard components.
    """

    def __init__(
        self,
        container: Any = None,
        event_bus: Any = None,
        state_store: Any = None,
        config: Any = None,
    ) -> None:
        self._container = container
        self._event_bus = event_bus or default_event_bus
        self._state = state_store or default_state_store
        self._config = config

        self._components: Dict[str, KernelComponent] = {}
        self._health: Dict[str, ComponentHealth] = {}
        self._status = KernelStatus.CREATED
        self._lock = threading.RLock()
        self._monitor: Optional[KernelHealthMonitor] = None
        self._last_report: Optional[KernelReport] = None
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None

    # ------------------------------------------------------------------ #
    # Read-only accessors
    # ------------------------------------------------------------------ #
    @property
    def container(self) -> Any:
        return self._container

    @property
    def event_bus(self) -> Any:
        return self._event_bus

    @property
    def state_store(self) -> Any:
        return self._state

    @property
    def config(self) -> Any:
        return self._config

    @property
    def status(self) -> KernelStatus:
        with self._lock:
            return self._status

    @property
    def status_name(self) -> str:
        return self.status.value

    @property
    def last_report(self) -> Optional[KernelReport]:
        return self._last_report

    @property
    def monitor_running(self) -> bool:
        monitor = self._monitor
        return monitor is not None and monitor.running

    def is_running(self) -> bool:
        return self.status in (KernelStatus.RUNNING,)

    def is_ready(self) -> bool:
        """True when the kernel has fully booted and is accepting work."""
        return self.is_running()

    # ------------------------------------------------------------------ #
    # Component registration
    # ------------------------------------------------------------------ #
    def register(self, component: KernelComponent) -> "AgentKernel":
        """Register a kernel component. Returns ``self`` for chaining."""
        if not isinstance(component, KernelComponent):
            raise TypeError(
                f"Expected a KernelComponent, got {type(component).__name__}"
            )
        name = component.name
        if not name:
            raise ValueError("KernelComponent.name must not be empty.")
        with self._lock:
            if name in self._components:
                raise KernelError(f"Component '{name}' is already registered.")
            self._components[name] = component
            self._health[name] = ComponentHealth(status=ComponentStatus.REGISTERED)
        if self._container is not None:
            try:
                component.wire(self._container)
            except Exception as exc:  # noqa: BLE001 - wiring must not break boot
                logger.warning(f"Component '{name}' failed to wire: {exc}")
        logger.info(f"Registered kernel component '{name}'")
        return self

    def register_many(self, components: List[KernelComponent]) -> "AgentKernel":
        for component in components:
            self.register(component)
        return self

    def unregister(self, name: str) -> bool:
        """Remove a component that is not currently running."""
        with self._lock:
            if self._status in (KernelStatus.BOOTING, KernelStatus.STARTING,
                                KernelStatus.RUNNING, KernelStatus.STOPPING):
                raise KernelError(
                    f"Cannot unregister '{name}' while the kernel is "
                    f"'{self._status.value}'."
                )
            removed = self._components.pop(name, None) is not None
            if removed:
                self._health.pop(name, None)
        if removed:
            logger.info(f"Unregistered kernel component '{name}'")
        return removed

    def get(self, name: str) -> Optional[KernelComponent]:
        return self._components.get(name)

    def names(self) -> List[str]:
        return list(self._components)

    def components(self) -> List[KernelComponent]:
        return list(self._components.values())

    # ------------------------------------------------------------------ #
    # Dependency resolution
    # ------------------------------------------------------------------ #
    def resolve_dependency_order(self, names: Optional[List[str]] = None) -> List[str]:
        """Resolve a deterministic topological start order.

        Dependencies always come before their dependents. Required
        dependencies that were never registered raise
        :class:`UnknownDependencyError`; cycles raise the container's
        :class:`~core.di.container.CircularDependencyError`.

        Args:
            names: Restrict resolution to a subset of components.
        """
        with self._lock:
            registry = dict(self._components)
        if names is not None:
            missing = [n for n in names if n not in registry]
            if missing:
                raise UnknownDependencyError(f"Unknown components: {missing}")
            registry = {n: registry[n] for n in names if n in registry}

        edges: Dict[str, set] = {}
        for name, comp in registry.items():
            deps: set = set()
            for dep in comp.dependencies:
                if dep in registry:
                    deps.add(dep)
                elif dep not in comp.optional_dependencies:
                    raise UnknownDependencyError(
                        f"Component '{name}' depends on unknown component "
                        f"'{dep}' (and does not declare it optional)."
                    )
            edges[name] = deps

        indegree = {name: len(deps) for name, deps in edges.items()}
        ready = [name for name in registry if indegree[name] == 0]
        heapq.heapify(ready)
        order: List[str] = []
        while ready:
            name = heapq.heappop(ready)
            order.append(name)
            for other, deps in edges.items():
                if name in deps:
                    deps.discard(name)
                    indegree[other] -= 1
                    if indegree[other] == 0:
                        heapq.heappush(ready, other)

        if len(order) != len(registry):
            unresolved = sorted(set(registry) - set(order))
            raise CircularDependencyError(
                f"Circular dependency detected among: {unresolved}"
            )
        return order

    # ------------------------------------------------------------------ #
    # Lifecycle: start / stop / restart / destroy
    # ------------------------------------------------------------------ #
    def start(self) -> KernelReport:
        """Boot the kernel: resolve order, start components, run monitor.

        Raises:
            KernelError: When started from an invalid state.
            KernelStartupError: When a critical component fails to start
                (already-started components are rolled back first).
        """
        with self._lock:
            if self._status in (KernelStatus.BOOTING, KernelStatus.STARTING,
                                KernelStatus.RUNNING, KernelStatus.STOPPING):
                raise KernelError(
                    f"Cannot start kernel from state '{self._status.value}'."
                )
            if not self._components:
                raise KernelError("Cannot start: no components registered.")
            self._started_at = datetime.now()
            self._status = KernelStatus.BOOTING
            self._publish(EV_KERNEL_BOOTING, {"started_at": self._started_at.isoformat()})
            order = self.resolve_dependency_order()
            self._status = KernelStatus.STARTING
            self._publish(EV_KERNEL_STARTING, {"order": order})
            self._update_state()

        records: Dict[str, ComponentStartRecord] = {}
        started: List[str] = []
        failed: List[str] = []

        for name in order:
            component = self._components[name]
            record = self._start_component(component)
            records[name] = record
            if record.ok:
                started.append(name)
            else:
                failed.append(name)
                if component.is_critical:
                    logger.error(
                        f"Critical component '{name}' failed to start — aborting boot"
                    )
                    self._status = KernelStatus.FAILED
                    self._publish(EV_KERNEL_START_FAILED, {
                        "component": name, "error": record.error,
                    })
                    self._update_state()
                    self._stop_started(started, records)
                    report = self._build_report(records, order)
                    self._last_report = report
                    raise KernelStartupError(
                        f"Critical component '{name}' failed to start: {record.error}"
                    ) from None

        with self._lock:
            self._status = KernelStatus.RUNNING
        self._monitor = self._build_monitor()
        self._monitor.start()
        self._publish(EV_KERNEL_RUNNING, {
            "components": started, "failed": failed,
        })
        self._update_state()
        report = self._build_report(records, order)
        self._last_report = report
        logger.info(
            f"Kernel started: {len(started)} components running, "
            f"{len(failed)} failed"
        )
        return report

    def shutdown(self) -> KernelReport:
        """Stop every component in reverse dependency order.

        Safe to call from any state — a stopped/created kernel is a no-op.
        Component shutdown errors are logged and collected in the report but
        never mask further shutdown work.
        """
        with self._lock:
            if self._status in (KernelStatus.CREATED, KernelStatus.STOPPED,
                                KernelStatus.DESTROYED, KernelStatus.FAILED):
                return self._build_report({}, [])
            if self._status == KernelStatus.STOPPING:
                raise KernelError("Kernel is already stopping.")
            self._status = KernelStatus.STOPPING
            self._publish(EV_KERNEL_STOPPING, {})
            self._update_state()

        # Stop the monitor first so it does not probe mid-shutdown.
        monitor = self._monitor
        self._monitor = None
        if monitor is not None:
            monitor.stop()

        order = self.resolve_dependency_order()
        records: Dict[str, ComponentStartRecord] = {}
        errors: List[str] = []
        for name in reversed(order):
            component = self._components.get(name)
            if component is None:
                continue
            record = self._stop_component(component)
            records[name] = record
            if not record.ok:
                errors.append(record.error or name)

        with self._lock:
            self._status = KernelStatus.STOPPED
            self._stopped_at = datetime.now()
        self._publish(EV_KERNEL_STOPPED, {"errors": errors})
        self._update_state()
        report = self._build_report(records, order)
        self._last_report = report
        if errors:
            logger.warning(f"Kernel shutdown completed with errors: {errors}")
        else:
            logger.info(f"Kernel stopped ({len(order)} components)")
        return report

    def restart(self) -> KernelReport:
        """Shut down (if running) and boot again."""
        if self._status in (KernelStatus.BOOTING, KernelStatus.STARTING,
                            KernelStatus.RUNNING, KernelStatus.STOPPING):
            self.shutdown()
        return self.start()

    def destroy(self) -> None:
        """Tear down the kernel permanently and drop all registrations."""
        if self._status in (KernelStatus.BOOTING, KernelStatus.STARTING,
                            KernelStatus.RUNNING, KernelStatus.STOPPING):
            self.shutdown()
        with self._lock:
            self._components.clear()
            self._health.clear()
            self._status = KernelStatus.DESTROYED
            self._last_report = None
        logger.info("Kernel destroyed")

    # ------------------------------------------------------------------ #
    # Health & status inspection
    # ------------------------------------------------------------------ #
    def check_health(self, name: Optional[str] = None):
        """Run a health probe now.

        With a component name, probes just that component and returns its
        updated :class:`ComponentHealth` (or None if it is not monitorable).
        Without a name, probes everything and returns a mapping of
        name → ComponentHealth. When the kernel has not started its monitor
        yet this falls back to a one-off probe.
        """
        monitor = self._monitor
        if monitor is not None:
            if name is not None:
                return monitor.check(name)
            return monitor.check_all()
        # One-off probe without a running monitor.
        monitor = self._build_monitor()
        if name is not None:
            return monitor.check(name)
        return monitor.check_all()

    def overall_health(self) -> str:
        """Aggregate health: ``"unhealthy"``, ``"degraded"`` or ``"healthy"``."""
        monitored = [
            h for h in self._health.values()
            if h.status in (ComponentStatus.UNHEALTHY, ComponentStatus.HEALTHY,
                            ComponentStatus.DEGRADED)
        ]
        if not monitored:
            return "healthy"
        if any(h.status == ComponentStatus.UNHEALTHY for h in monitored):
            return "unhealthy"
        if any(h.status == ComponentStatus.DEGRADED for h in monitored):
            return "degraded"
        return "healthy"

    def component_status(self, name: str) -> Optional[ComponentStatus]:
        health = self._health.get(name)
        return health.status if health is not None else None

    def health_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return name → serialized health record for every component."""
        return {name: h.as_dict() for name, h in self._health.items()}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _start_component(self, component: KernelComponent) -> ComponentStartRecord:
        name = component.name
        with self._lock:
            self._health[name].status = ComponentStatus.STARTING
        started = time.monotonic()
        try:
            component.start()
            ok = True
            error = None
        except Exception as exc:  # noqa: BLE001 - failures are recorded
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            logger.error(f"Component '{name}' failed to start: {error}")
        duration_ms = (time.monotonic() - started) * 1000.0
        with self._lock:
            self._health[name].status = (
                ComponentStatus.RUNNING if ok else ComponentStatus.FAILED
            )
        if ok:
            self._publish(EV_KERNEL_COMPONENT_STARTED, {
                "component": name, "duration_ms": duration_ms,
            })
        else:
            self._publish(EV_KERNEL_COMPONENT_FAILED, {
                "component": name, "error": error,
            })
        self._update_state()
        return ComponentStartRecord(
            name=name, ok=ok, duration_ms=duration_ms, error=error,
        )

    def _stop_component(self, component: KernelComponent) -> ComponentStartRecord:
        name = component.name
        with self._lock:
            self._health[name].status = ComponentStatus.STOPPING
        started = time.monotonic()
        try:
            component.stop()
            ok = True
            error = None
        except Exception as exc:  # noqa: BLE001 - failures are recorded
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            logger.error(f"Component '{name}' failed to stop: {error}")
        duration_ms = (time.monotonic() - started) * 1000.0
        with self._lock:
            self._health[name].status = (
                ComponentStatus.STOPPED if ok else ComponentStatus.FAILED
            )
        self._publish(EV_KERNEL_COMPONENT_STOPPED, {
            "component": name, "ok": ok, "duration_ms": duration_ms,
        })
        self._update_state()
        return ComponentStartRecord(
            name=name, ok=ok, duration_ms=duration_ms, error=error,
        )

    def _stop_started(self, started: List[str],
                      records: Dict[str, ComponentStartRecord]) -> None:
        """Roll back already-started components after a failed boot."""
        started_set = set(started)
        order = [n for n in self.resolve_dependency_order() if n in started_set]
        for name in reversed(order):
            component = self._components.get(name)
            if component is None:
                continue
            records[name] = self._stop_component(component)
        logger.warning(
            f"Rolled back {len(started_set)} started component(s) after "
            f"aborted boot"
        )

    def _build_monitor(self) -> KernelHealthMonitor:
        interval = min(
            (c.health_interval for c in self._components.values()
             if c.health_interval and c.health_interval > 0),
            default=30.0,
        )
        return KernelHealthMonitor(
            self._components,
            self._health,
            on_status_change=self._on_component_health_change,
            check_interval=float(interval),
        )

    def _on_component_health_change(self, name: str,
                                    health: ComponentHealth) -> None:
        self._publish(EV_KERNEL_HEALTH_CHANGED, {
            "component": name, "health": health.as_dict(),
        })
        self._update_state()

    def _build_report(self, records: Dict[str, ComponentStartRecord],
                      order: List[str]) -> KernelReport:
        started = self._started_at
        completed = self._stopped_at or datetime.now()
        duration_ms = 0.0
        if started is not None:
            duration_ms = (completed - started).total_seconds() * 1000.0
        return KernelReport(
            status=self._status,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
            order=list(order),
            components=dict(records),
        )

    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            self._event_bus.emit(event, payload)
        except Exception as exc:  # noqa: BLE001 - events must not break boot
            logger.debug(f"Failed to publish '{event}': {exc}")

    def _update_state(self) -> None:
        """Mirror kernel status and component health into the state store."""
        if self._state is None:
            return
        try:
            self._state.set("kernel.status", {
                "status": self._status.value,
                "updated_at": datetime.now().isoformat(),
            })
            self._state.set("kernel.components", {
                name: h.as_dict() for name, h in self._health.items()
            })
        except Exception as exc:  # noqa: BLE001 - state is best-effort
            logger.debug(f"Kernel state sync failed: {exc}")

