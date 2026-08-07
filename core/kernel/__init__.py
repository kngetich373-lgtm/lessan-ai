"""AgentKernel — lifecycle management, dependency resolution and health
monitoring for the Lessan AI runtime.

The kernel is the composition root of the application: subsystems implement
:class:`KernelComponent` and register themselves with an :class:`AgentKernel`
instance, which then resolves the dependency graph, boots every component in
order, monitors health on a background thread, and shuts everything down
gracefully in reverse order.

Public API
----------
* :class:`AgentKernel` — the runtime coordinator (start/stop/restart/destroy,
  dependency resolution, health inspection).
* :class:`KernelComponent` — base class every kernel-managed subsystem
  implements (lifecycle hooks, dependency declaration, health probe).
* :class:`KernelHealthMonitor` — background daemon thread that probes
  components on an interval and publishes status transitions.
* :class:`KernelStatus` / :class:`ComponentStatus` — lifecycle enums.
* :class:`ComponentHealth` / :class:`ComponentStartRecord` / :class:`KernelReport`
  — data models with ``as_dict()`` serialization.
* :func:`register_kernel` — idempotent DI wiring for the container.
"""

from core.kernel.component import KernelComponent
from core.kernel.health import KernelHealthMonitor
from core.kernel.kernel import (
    AgentKernel,
    KernelError,
    KernelStartupError,
    UnknownDependencyError,
)
from core.kernel.models import (
    ComponentHealth,
    ComponentStartRecord,
    ComponentStatus,
    KernelReport,
    KernelStatus,
)

__all__ = [
    "AgentKernel",
    "KernelComponent",
    "KernelHealthMonitor",
    "KernelStatus",
    "ComponentStatus",
    "ComponentHealth",
    "ComponentStartRecord",
    "KernelReport",
    "KernelError",
    "KernelStartupError",
    "UnknownDependencyError",
]
