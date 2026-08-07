"""KernelComponent — the contract every kernel-managed subsystem implements.

Components declare their dependency graph (``dependencies`` /
``optional_dependencies``) and their lifecycle hooks. The
:class:`~core.kernel.kernel.AgentKernel` resolves the graph, starts every
component in dependency order, monitors health, and shuts everything down in
reverse order.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from core.logging import get_logger


class KernelComponent(ABC):
    """Base class for subsystems managed by the AgentKernel.

    Subclasses declare:

    * ``name`` — unique identifier used as the node key in the kernel's
      dependency graph.
    * ``dependencies`` — names of components that must start first.
    * ``optional_dependencies`` — dependencies that are used only when present
      (a missing optional dependency never blocks startup).
    * ``health_interval`` — seconds between health probes (used by the
      kernel's monitor; ``0``/``None`` means "not monitored").

    And implement:

    * :meth:`start` / :meth:`stop` — lifecycle hooks.
    * :meth:`health_check` — optional live probe; return ``True``/``False``
      when the component can be probed and ``None`` when it cannot.
    """

    #: Unique identifier used as the dependency-graph node key.
    name: str = "component"
    #: Human-readable label for logs/reports.
    display_name: str = ""
    #: One-line description of the subsystem.
    description: str = ""
    #: Names of components that must start before this one.
    dependencies: List[str] = []
    #: Names of components that are used only when present.
    optional_dependencies: List[str] = []
    #: Seconds between health probes (``None``/``0`` disables monitoring).
    health_interval: Optional[float] = 30.0

    def __init__(self) -> None:
        self.logger = get_logger(f"kernel.component.{self.name}")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @abstractmethod
    def start(self) -> None:
        """Bring the subsystem up. Raise to signal a failed startup."""

    @abstractmethod
    def stop(self) -> None:
        """Tear the subsystem down. Raise to signal a failed shutdown."""

    def health_check(self) -> Optional[bool]:
        """Return ``True``/``False`` when the component can be probed.

        Return ``None`` (the default) for components that do not support
        live health checks. Implementations must never block for more than
        a few seconds; the kernel monitor treats slow probes as degraded.
        """
        return None

    # ------------------------------------------------------------------ #
    # Optional hooks
    # ------------------------------------------------------------------ #
    @property
    def is_critical(self) -> bool:
        """Whether a failed startup must abort the whole kernel boot.

        Critical subsystems (config, event bus, scheduler, ...) abort the
        boot. Non-critical subsystems (plugins, workspaces, ...) log a
        warning and let the kernel continue.
        """
        return False

    def wire(self, container: Any) -> None:
        """Optional hook called by the kernel when a DI container is available.

        Components that need services from the container can resolve them
        here, before the kernel starts anything.
        """

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #
    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<{type(self).__name__} name={self.name!r}>"
