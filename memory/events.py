"""Memory event topics and publish helpers for the Event Bus.

Subsystems subscribe to these topics without importing providers or the
MemoryManager. Follows the same pattern as ``core.model_router.router``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.event_bus import event_bus as global_event_bus
from core.logging import get_logger

logger = get_logger("memory.events")

# ---------------------------------------------------------------------------
# Event topics published by the Unified Memory System
# ---------------------------------------------------------------------------
EV_MEMORY_STORED = "memory.stored"
EV_MEMORY_RETRIEVED = "memory.retrieved"
EV_MEMORY_UPDATED = "memory.updated"
EV_MEMORY_DELETED = "memory.deleted"
EV_MEMORY_SEARCHED = "memory.searched"
EV_MEMORY_SUMMARIZED = "memory.summarized"
EV_MEMORY_ARCHIVED = "memory.archived"
EV_MEMORY_RESTORED = "memory.restored"
EV_PROVIDER_REGISTERED = "memory.provider_registered"
EV_PROVIDER_UNREGISTERED = "memory.provider_unregistered"

ALL_MEMORY_EVENTS = (
    EV_MEMORY_STORED,
    EV_MEMORY_RETRIEVED,
    EV_MEMORY_UPDATED,
    EV_MEMORY_DELETED,
    EV_MEMORY_SEARCHED,
    EV_MEMORY_SUMMARIZED,
    EV_MEMORY_ARCHIVED,
    EV_MEMORY_RESTORED,
    EV_PROVIDER_REGISTERED,
    EV_PROVIDER_UNREGISTERED,
)


def emit_memory_event(
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    bus: Any = None,
) -> None:
    """Publish a memory event on the event bus.

    Failures are logged and swallowed so memory operations remain resilient
    even if a subscriber raises.
    """
    bus = bus or global_event_bus
    data = payload or {}
    try:
        # EventBus API is ``emit``; keep a ``publish`` fallback for any
        # thin wrappers that may expose that name.
        if hasattr(bus, "emit"):
            bus.emit(event, data)
        elif hasattr(bus, "publish"):
            bus.publish(event, data)
        else:
            logger.warning(f"Event bus has no emit/publish for '{event}'")
    except Exception as exc:  # noqa: BLE001 - keep memory path resilient
        logger.warning(f"Failed to emit memory event '{event}': {exc}")
