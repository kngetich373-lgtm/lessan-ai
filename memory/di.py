"""Dependency Injection registration for the Unified Memory System.

Call :func:`register_memory_system` once at application startup. Subsystems
then resolve :class:`MemoryManager` or :class:`MemoryStore` (orchestrator)
through their DI container without direct imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.logging import get_logger

if TYPE_CHECKING:
    from core.di.container import Container

logger = get_logger("memory.di")


def register_memory_system(
    container: "Container",
    *,
    event_bus: Optional[object] = None,
    state_store: Optional[object] = None,
) -> None:
    """Register all Unified Memory System components in the DI container.

    Idempotent — safe to call multiple times. Registers:
      - :class:`~memory.registry.MemoryRegistry`
      - :class:`~memory.manager.MemoryManager`
      - :class:`~memory.adapters.OrchestratorMemoryStore` (as MemoryStore ABC)
      - Default providers (InMemory, LongTerm, Conversation)

    Args:
        container: The DI container (core.di.Container).
        event_bus: Optional EventBus instance for memory events.
        state_store: Optional StateStore instance for metadata mirroring.
    """
    from core.orchestrator.interfaces import MemoryStore as IMemoryStore

    from memory.adapters import (
        ConversationMemoryProvider,
        InMemoryProvider,
        LongTermMemoryProvider,
        OrchestratorMemoryStore,
    )
    from memory.manager import MemoryManager
    from memory.registry import MemoryRegistry
    from memory.scopes import MemoryScope

    # Skip if already registered
    if container.has("memory.registry"):
        logger.debug("Memory system already registered, skipping.")
        return

    logger.info("Registering Unified Memory System components...")

    # 1. Registry (singleton instance)
    registry = MemoryRegistry(event_bus=event_bus)
    container.register_instance(type(registry), registry)
    
    # 2. Manager (singleton instance)
    manager = MemoryManager(registry, event_bus=event_bus, state_store=state_store)
    container.register_instance(MemoryManager, manager)

    # 3. Orchestrator adapter (MemoryStore ABC)
    orch_store = OrchestratorMemoryStore(manager)
    container.register_instance(IMemoryStore, orch_store)

    # 4. Default providers
    _register_default_providers(registry)

    logger.info(
        f"Memory system registered: {len(registry)} providers, "
        f"{len(manager.available_scopes())} scopes"
    )


def _register_default_providers(registry: "MemoryRegistry") -> None:
    """Register built-in memory providers."""
    from memory.adapters import (
        ConversationMemoryProvider,
        InMemoryProvider,
        LongTermMemoryProvider,
    )
    from memory.scopes import MemoryScope

    # Long-term USER/GLOBAL knowledge
    long_term = LongTermMemoryProvider(name="long_term")
    registry.register(long_term)

    # Conversation SESSION
    conversation = ConversationMemoryProvider(name="conversation")
    registry.register(conversation)

    # Generic in-memory for AGENT, WORKSPACE, PROJECT, WORKFLOW
    in_memory = InMemoryProvider(
        name="in_memory",
        scopes=[
            MemoryScope.AGENT,
            MemoryScope.WORKSPACE,
            MemoryScope.PROJECT,
            MemoryScope.WORKFLOW,
        ],
    )
    registry.register(in_memory)

    logger.debug(
        f"Registered default providers: {', '.join(p.name for p in [long_term, conversation, in_memory])}"
    )


def unregister_memory_system(container: "Container") -> None:
    """Remove memory system from DI (test teardown helper)."""
    from memory.manager import MemoryManager
    from memory.registry import MemoryRegistry
    
    for service_type in [MemoryRegistry, MemoryManager]:
        try:
            container.unregister(service_type)
        except Exception:
            pass
    logger.info("Memory system unregistered from DI container.")
