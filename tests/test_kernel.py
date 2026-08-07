"""Validation tests for the AgentKernel subsystem.

Run with:  python3 -m unittest tests.test_kernel -v

Covers:
 1. Registration: register/unregister/get/names/components, duplicate
    registration and invalid-state unregister.
 2. Dependency resolution: topological start order, unknown required
    dependency, tolerated missing optional dependency, cycle detection.
 3. Lifecycle: full boot (order + report), graceful shutdown in reverse
    order, restart, destroy, guard rails (double start, empty boot).
 4. Failure handling: critical component aborts the boot and rolls back
    already-started components; non-critical failures are tolerated.
 5. Health monitoring: background probes, one-off check, overall_health,
    health snapshot.
 6. Event bus and state store integration.
 7. DI wiring: register_kernel is idempotent and returns a singleton.
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.di.container import CircularDependencyError, Container
from core.event_bus import event_bus as global_event_bus
from core.kernel.component import KernelComponent
from core.kernel.di import register_kernel
from core.kernel.health import KernelHealthMonitor
from core.kernel.kernel import (
    AgentKernel,
    EV_KERNEL_RUNNING,
    KernelError,
    KernelStartupError,
    UnknownDependencyError,
)
from core.kernel.models import (
    ComponentHealth,
    ComponentStatus,
    KernelReport,
    KernelStatus,
)
from core.state import state as global_state_store


class _TraceComponent(KernelComponent):
    """Dummy component that records lifecycle calls on a shared trace list."""

    name = "trace"

    def __init__(self, trace, *, start=None, stop=None, health=None,
                 critical=False):
        super().__init__()
        self._trace = trace
        self._start = start
        self._stop = stop
        self._health = health
        self._critical = critical

    @property
    def is_critical(self) -> bool:
        return self._critical

    def start(self):
        self._trace.append(f"{self.name}.start")
        if self._start:
            self._start()

    def stop(self):
        self._trace.append(f"{self.name}.stop")
        if self._stop:
            self._stop()

    def health_check(self):
        if self._health is not None:
            return self._health()
        return True if self.health_interval else None


def _comp(name, deps=(), opt=(), health_interval=0, **kwargs):
    return type(
        f"Comp_{name}",
        (_TraceComponent,),
        {"name": name, "dependencies": list(deps),
         "optional_dependencies": list(opt),
         "health_interval": health_interval},
    )(kwargs.pop("trace", []), **kwargs)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.kernel = AgentKernel(event_bus=global_event_bus)
        self.trace = []

    def test_register_and_inspect(self):
        a = _comp("a", trace=self.trace)
        self.kernel.register(a)
        self.assertIs(self.kernel.get("a"), a)
        self.assertEqual(self.kernel.names(), ["a"])
        self.assertEqual(self.kernel.components(), [a])
        self.assertEqual(self.kernel.component_status("a"),
                         ComponentStatus.REGISTERED)

    def test_register_many_and_chaining(self):
        a, b = _comp("a", trace=self.trace), _comp("b", trace=self.trace)
        result = self.kernel.register_many([a, b])
        self.assertIs(result, self.kernel)
        self.assertEqual(set(self.kernel.names()), {"a", "b"})

    def test_duplicate_registration_raises(self):
        self.kernel.register(_comp("a", trace=self.trace))
        with self.assertRaises(KernelError):
            self.kernel.register(_comp("a", trace=self.trace))

    def test_unregister(self):
        a = _comp("a", trace=self.trace)
        self.kernel.register(a)
        self.assertTrue(self.kernel.unregister("a"))
        self.assertFalse(self.kernel.unregister("a"))
        self.assertIsNone(self.kernel.get("a"))

    def test_unregister_while_running_raises(self):
        self.kernel.register(_comp("a", trace=self.trace))
        self.kernel.start()
        try:
            with self.assertRaises(KernelError):
                self.kernel.unregister("a")
        finally:
            self.kernel.shutdown()

    def test_registration_rejects_non_component(self):
        with self.assertRaises(TypeError):
            self.kernel.register(object())  # type: ignore[arg-type]


class DependencyResolutionTests(unittest.TestCase):
    def setUp(self):
        self.kernel = AgentKernel(event_bus=global_event_bus)
        self.trace = []

    def test_topological_order(self):
        self.kernel.register_many([
            _comp("c", deps=["a", "b"], trace=self.trace),
            _comp("a", trace=self.trace),
            _comp("b", deps=["a"], trace=self.trace),
        ])
        order = self.kernel.resolve_dependency_order()
        self.assertEqual(order, ["a", "b", "c"])

    def test_order_is_deterministic(self):
        self.kernel.register_many([
            _comp(n, trace=self.trace) for n in ("beta", "alpha", "gamma")
        ])
        first = self.kernel.resolve_dependency_order()
        second = self.kernel.resolve_dependency_order()
        self.assertEqual(first, second)

    def test_unknown_required_dependency_raises(self):
        self.kernel.register(_comp("a", deps=["missing"], trace=self.trace))
        with self.assertRaises(UnknownDependencyError):
            self.kernel.resolve_dependency_order()

    def test_missing_optional_dependency_is_tolerated(self):
        self.kernel.register(
            _comp("a", deps=[], opt=["ghost"], trace=self.trace)
        )
        self.assertEqual(self.kernel.resolve_dependency_order(), ["a"])

    def test_cycle_detection(self):
        self.kernel.register_many([
            _comp("x", deps=["y"], trace=self.trace),
            _comp("y", deps=["x"], trace=self.trace),
        ])
        with self.assertRaises(CircularDependencyError):
            self.kernel.resolve_dependency_order()

    def test_resolution_with_subset(self):
        self.kernel.register_many([
            _comp("a", trace=self.trace),
            _comp("b", deps=["a"], trace=self.trace),
            _comp("c", trace=self.trace),
        ])
        self.assertEqual(self.kernel.resolve_dependency_order(["b", "a"]),
                         ["a", "b"])
        with self.assertRaises(UnknownDependencyError):
            self.kernel.resolve_dependency_order(["nope"])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.kernel = AgentKernel(event_bus=global_event_bus)
        self.trace = []

    def test_full_boot_and_shutdown_order(self):
        self.kernel.register_many([
            _comp("charlie", deps=["alpha", "bravo"], trace=self.trace),
            _comp("alpha", trace=self.trace),
            _comp("bravo", deps=["alpha"], trace=self.trace),
        ])
        report = self.kernel.start()
        self.assertIsInstance(report, KernelReport)
        self.assertEqual(self.kernel.status, KernelStatus.RUNNING)
        self.assertTrue(self.kernel.is_running())
        self.assertTrue(self.kernel.is_ready())
        self.assertTrue(report.succeeded)
        self.assertEqual(report.order, ["alpha", "bravo", "charlie"])
        self.assertEqual(set(report.components), {"alpha", "bravo", "charlie"})
        self.assertTrue(all(r.ok for r in report.components.values()))

        shutdown = self.kernel.shutdown()
        self.assertEqual(self.kernel.status, KernelStatus.STOPPED)
        self.assertTrue(shutdown.succeeded)
        self.assertEqual(
            self.trace,
            ["alpha.start", "bravo.start", "charlie.start",
             "charlie.stop", "bravo.stop", "alpha.stop"],
        )
        self.assertIs(self.kernel.last_report, shutdown)

    def test_cannot_start_twice(self):
        self.kernel.register(_comp("a", trace=self.trace))
        self.kernel.start()
        try:
            with self.assertRaises(KernelError):
                self.kernel.start()
        finally:
            self.kernel.shutdown()

    def test_cannot_start_empty_kernel(self):
        with self.assertRaises(KernelError):
            self.kernel.start()

    def test_shutdown_when_not_running_is_noop(self):
        report = self.kernel.shutdown()
        # A never-started kernel stays CREATED; shutdown is a safe no-op.
        self.assertEqual(self.kernel.status, KernelStatus.CREATED)
        self.assertEqual(report.failed_components, [])

    def test_restart(self):
        self.kernel.register(_comp("a", trace=self.trace))
        first = self.kernel.start()
        self.assertEqual(first.status, KernelStatus.RUNNING)
        second = self.kernel.restart()
        self.assertEqual(self.kernel.status, KernelStatus.RUNNING)
        self.assertEqual(self.trace, ["a.start", "a.stop", "a.start"])

    def test_destroy_drops_everything(self):
        self.kernel.register(_comp("a", trace=self.trace))
        self.kernel.start()
        self.kernel.destroy()
        self.assertEqual(self.kernel.status, KernelStatus.DESTROYED)
        self.assertEqual(self.kernel.names(), [])


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.kernel = AgentKernel(event_bus=global_event_bus)
        self.trace = []

    def test_critical_failure_aborts_and_rolls_back(self):
        def boom():
            raise RuntimeError("boom")

        self.kernel.register_many([
            _comp("ok", trace=self.trace),
            _comp("boom", deps=["ok"], start=boom, critical=True,
                  trace=self.trace),
        ])
        with self.assertRaises(KernelStartupError):
            self.kernel.start()
        self.assertEqual(self.kernel.status, KernelStatus.FAILED)
        self.assertFalse(self.kernel.is_running())
        # The already-started "ok" component must have been rolled back.
        self.assertEqual(self.trace, ["ok.start", "boom.start", "ok.stop"])

    def test_non_critical_failure_does_not_abort(self):
        def fail():
            raise ValueError("soft")

        self.kernel.register_many([
            _comp("ok", trace=self.trace),
            _comp("soft", deps=["ok"], start=fail, critical=False,
                  trace=self.trace),
        ])
        report = self.kernel.start()
        self.assertEqual(self.kernel.status, KernelStatus.RUNNING)
        self.assertEqual(report.failed_components, ["soft"])
        self.assertEqual(self.kernel.component_status("soft"),
                         ComponentStatus.FAILED)
        self.kernel.shutdown()

    def test_stop_error_does_not_mask_shutdown(self):
        def bad_stop():
            raise RuntimeError("stop boom")

        self.kernel.register(_comp("a", stop=bad_stop, trace=self.trace))
        self.kernel.start()
        report = self.kernel.shutdown()
        self.assertEqual(self.kernel.status, KernelStatus.STOPPED)
        self.assertFalse(report.components["a"].ok)
        self.assertIsNotNone(report.components["a"].error)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.kernel = AgentKernel(event_bus=global_event_bus)
        self.trace = []

    def test_background_probe_updates_health(self):
        self.kernel.register(_comp("a", health_interval=0.05, trace=self.trace))
        self.kernel.start()
        try:
            time.sleep(0.25)
            health = self.kernel.check_health("a")
            self.assertIsNotNone(health)
            self.assertEqual(health.status, ComponentStatus.HEALTHY)
            self.assertIsInstance(health, ComponentHealth)
            self.assertTrue(health.is_monitored)
        finally:
            self.kernel.shutdown()

    def test_one_off_probe_without_monitor(self):
        self.kernel.register(_comp("a", trace=self.trace))
        # No monitorable health interval -> not monitored -> None.
        self.assertIsNone(self.kernel.check_health("a"))

    def test_unmonitorable_component(self):
        self.kernel.register(_comp("a", health_interval=0, trace=self.trace))
        self.kernel.start()
        try:
            time.sleep(0.15)
            self.assertIsNone(self.kernel.check_health("a"))
        finally:
            self.kernel.shutdown()

    def test_failed_component_is_never_marked_healthy(self):
        def fail():
            raise ValueError("soft")

        self.kernel.register_many([
            _comp("soft", start=fail, health_interval=0.05,
                  health=lambda: True, trace=self.trace),
        ])
        self.kernel.start()
        try:
            # The monitor must not flip a FAILED component to HEALTHY.
            time.sleep(0.25)
            health = self.kernel.check_health("soft")
            self.assertIsNone(health)
            self.assertEqual(self.kernel.component_status("soft"),
                             ComponentStatus.FAILED)
        finally:
            self.kernel.shutdown()

    def test_overall_health_aggregation(self):
        self.kernel.register_many([
            _comp("ok", health_interval=0.05, trace=self.trace),
            _comp("bad", health_interval=0.05, health=lambda: False,
                  trace=self.trace),
        ])
        self.kernel.start()
        try:
            time.sleep(0.25)
            self.assertEqual(self.kernel.overall_health(), "unhealthy")
        finally:
            self.kernel.shutdown()

    def test_health_snapshot_shape(self):
        self.kernel.register(_comp("a", health_interval=0.05, trace=self.trace))
        self.kernel.start()
        try:
            snapshot = self.kernel.health_snapshot()
            self.assertIn("a", snapshot)
            self.assertEqual(snapshot["a"]["status"],
                             ComponentStatus.HEALTHY.value)
        finally:
            self.kernel.shutdown()


class IntegrationTests(unittest.TestCase):
    def test_events_are_published(self):
        fired = []

        def on_running(payload):
            fired.append(payload)

        global_event_bus.subscribe(EV_KERNEL_RUNNING, on_running)
        kernel = AgentKernel(event_bus=global_event_bus)
        kernel.register(_comp("a"))
        try:
            kernel.start()
            self.assertTrue(fired)
            self.assertEqual(fired[0]["components"], ["a"])
        finally:
            kernel.shutdown()

    def test_state_store_mirroring(self):
        kernel = AgentKernel(event_bus=global_event_bus,
                             state_store=global_state_store)
        kernel.register(_comp("a"))
        kernel.start()
        status = global_state_store.get("kernel.status")
        self.assertEqual(status["status"], "running")
        kernel.shutdown()
        status = global_state_store.get("kernel.status")
        self.assertEqual(status["status"], "stopped")
        components = global_state_store.get("kernel.components")
        self.assertEqual(components["a"]["status"], "stopped")

    def test_register_kernel_is_idempotent_singleton(self):
        container = Container()
        first = register_kernel(container, event_bus=global_event_bus,
                                state_store=global_state_store)
        second = register_kernel(container, event_bus=global_event_bus,
                                 state_store=global_state_store)
        self.assertIs(first, second)
        self.assertIs(container.resolve(AgentKernel), first)

    def test_monitor_class_starts_and_stops(self):
        components = {"a": _comp("a", health_interval=0.05)}
        state = {"a": ComponentHealth(status=ComponentStatus.RUNNING)}
        monitor = KernelHealthMonitor(components, state, check_interval=0.05)
        monitor.start()
        try:
            self.assertTrue(monitor.running)
            time.sleep(0.15)
            self.assertEqual(state["a"].status, ComponentStatus.HEALTHY)
        finally:
            monitor.stop()
        self.assertFalse(monitor.running)


if __name__ == "__main__":
    unittest.main()
