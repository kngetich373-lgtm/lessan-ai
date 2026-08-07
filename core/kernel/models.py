"""Data models for the AgentKernel lifecycle and health monitoring."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class KernelStatus(Enum):
    """High-level lifecycle state of the :class:`~core.kernel.kernel.AgentKernel`.

    States follow a strict progression:

    * ``CREATED`` → ``BOOTING`` → ``STARTING`` → ``RUNNING`` on startup
    * ``RUNNING`` → ``STOPPING`` → ``STOPPED`` on shutdown
    * ``FAILED`` when a critical component aborts the boot
    * ``DESTROYED`` after :meth:`~core.kernel.kernel.AgentKernel.destroy`
    """

    CREATED = "created"
    BOOTING = "booting"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DESTROYED = "destroyed"


class ComponentStatus(Enum):
    """Per-component lifecycle/health status."""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ComponentHealth:
    """Mutable health record for a single kernel component."""

    status: ComponentStatus = ComponentStatus.REGISTERED
    latency_ms: float = 0.0
    last_checked: Optional[datetime] = None
    error: Optional[str] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    @property
    def is_healthy(self) -> bool:
        """True when the component is serving traffic or merely degraded."""
        return self.status in (
            ComponentStatus.HEALTHY,
            ComponentStatus.DEGRADED,
            ComponentStatus.RUNNING,
        )

    @property
    def is_monitored(self) -> bool:
        """True once the health monitor has probed this component."""
        return self.last_checked is not None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 3),
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "error": self.error,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
        }


@dataclass
class ComponentStartRecord:
    """Outcome of one start/stop attempt for a kernel component."""

    name: str
    ok: bool
    duration_ms: float
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
        }


@dataclass
class KernelReport:
    """Snapshot of a full boot/shutdown run produced by the kernel."""

    status: KernelStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    order: List[str] = field(default_factory=list)
    components: Dict[str, ComponentStartRecord] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        """True when the run finished in a terminal healthy state."""
        return self.status in (KernelStatus.RUNNING, KernelStatus.STOPPED)

    @property
    def failed_components(self) -> List[str]:
        return [n for n, r in self.components.items() if not r.ok]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": round(self.duration_ms, 3),
            "order": list(self.order),
            "components": {n: r.as_dict() for n, r in self.components.items()},
        }
