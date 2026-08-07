"""Event topics and publish helpers for the Professional Document Intelligence
System.

Subsystems subscribe to these topics without importing concrete generator
classes. Follows the same failure-tolerant pattern as ``memory.events``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.event_bus import event_bus as global_event_bus
from core.logging import get_logger

logger = get_logger("documents.events")

# ---------------------------------------------------------------------------
# Event topics published by the document system
# ---------------------------------------------------------------------------
EV_DOCUMENT_STARTED = "documents.started"
EV_DOCUMENT_KIND_RESOLVED = "documents.kind_resolved"
EV_DOCUMENT_TEMPLATE_SELECTED = "documents.template_selected"
EV_DOCUMENT_CONTENT_READY = "documents.content_ready"
EV_DOCUMENT_FORMATTED = "documents.formatted"
EV_DOCUMENT_EXPORTED = "documents.exported"
EV_DOCUMENT_GENERATED = "documents.generated"
EV_DOCUMENT_FAILED = "documents.failed"

ALL_DOCUMENT_EVENTS = (
    EV_DOCUMENT_STARTED,
    EV_DOCUMENT_KIND_RESOLVED,
    EV_DOCUMENT_TEMPLATE_SELECTED,
    EV_DOCUMENT_CONTENT_READY,
    EV_DOCUMENT_FORMATTED,
    EV_DOCUMENT_EXPORTED,
    EV_DOCUMENT_GENERATED,
    EV_DOCUMENT_FAILED,
)


def emit_document_event(
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    bus: Any = None,
) -> None:
    """Publish a document event on the event bus.

    Failures are logged and swallowed so document generation stays resilient
    even if a subscriber raises.
    """
    bus = bus or global_event_bus
    data = payload or {}
    try:
        if hasattr(bus, "emit"):
            bus.emit(event, data)
        elif hasattr(bus, "publish"):
            bus.publish(event, data)
        else:
            logger.warning(f"Event bus has no emit/publish for '{event}'")
    except Exception as exc:  # noqa: BLE001 - keep generation path resilient
        logger.warning(f"Failed to emit document event '{event}': {exc}")
