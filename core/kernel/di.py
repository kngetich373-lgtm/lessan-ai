"""Dependency Injection wiring for the AgentKernel subsystem.

Call :func:`register_kernel` once at application startup (idempotent — safe
to call repeatedly). It constructs the :class:`~core.kernel.kernel.AgentKernel`
composition root, bound to the application's DI container, event bus, state
store and configuration, and registers it as a singleton so any subsystem can
resolve ``AgentKernel`` to start/stop the runtime, inspect component health or
hook into kernel lifecycle events.

The kernel itself is the composition root: components (config, event bus,
scheduler, model router, ...) implement :class:`KernelComponent` and are
registered *on* the kernel via :meth:`AgentKernel.register`, not directly in
the DI container.
"""

from typing import Any, Optional

from core.di.container import container as global_container
from core.event_bus import event_bus as global_event_bus
from core.state import state as global_state_store

from core.kernel.kernel import AgentKernel


def register_kernel(
    container: Any = None,
    *,
    config: Any = None,
    event_bus: Any = None,
    state_store: Any = None,
) -> AgentKernel:
    """Register the AgentKernel singleton with a DI container.

    Idempotent: re-invoking the function returns the already-constructed
    kernel and never clobbers registrations.

    Args:
        container: The DI container to register into. Defaults to the global
            container.
        config: The configuration manager passed to the kernel (and, through
            it, to standard components). Defaults to the global config.
        event_bus: Event bus the kernel publishes lifecycle events on.
            Defaults to the global event bus.
        state_store: State store the kernel mirrors status into.
            Defaults to the global state store.

    Returns:
        The constructed :class:`AgentKernel` (singleton).
    """
    container = container or global_container

    if container.has(AgentKernel):
        return container.resolve(AgentKernel)

    if event_bus is None:
        event_bus = global_event_bus
    if state_store is None:
        state_store = global_state_store
    if config is None:
        try:
            from core.configuration.config import config as global_config

            config = global_config
        except Exception:  # noqa: BLE001 - config is optional
            config = None

    kernel = AgentKernel(
        container=container,
        event_bus=event_bus,
        state_store=state_store,
        config=config,
    )
    container.register_instance(AgentKernel, kernel)
    return kernel


# Auto-register on import only when the global container is empty.
# This keeps the module import-safe when applications provide their own
# container wiring.
if not global_container.has(AgentKernel):
    register_kernel()
