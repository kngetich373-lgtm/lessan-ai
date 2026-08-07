"""Event topics and publish helpers for the File & Command Control System.

Subsystems subscribe to these topics without importing concrete file-manager
or command-executor classes. Follows the same failure-tolerant pattern as
``memory.events`` and ``documents.events``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.event_bus import event_bus as global_event_bus
from core.logging import get_logger

logger = get_logger("automation.events")

# --------------------------------------------------------------------------- #
# Event topics published by the File & Command Control System
# --------------------------------------------------------------------------- #
EV_FILE_CREATED = "automation.file_created"
EV_FILE_MODIFIED = "automation.file_modified"
EV_FILE_DELETED = "automation.file_deleted"
EV_FILE_OPENED = "automation.file_opened"
EV_FILE_RENAMED = "automation.file_renamed"
EV_FILE_MOVED = "automation.file_moved"
EV_FILE_COPIED = "automation.file_copied"
EV_FOLDER_CREATED = "automation.folder_created"
EV_FOLDER_DELETED = "automation.folder_deleted"
EV_BATCH_COMPLETED = "automation.batch_completed"
EV_SCAN_COMPLETED = "automation.scan_completed"
EV_COMMAND_STARTED = "automation.command_started"
EV_COMMAND_COMPLETED = "automation.command_completed"
EV_COMMAND_FAILED = "automation.command_failed"
EV_PERMISSION_CHECKED = "automation.permission_checked"
EV_PERMISSION_CONFIRMED = "automation.permission_confirmed"
EV_PERMISSION_DENIED = "automation.permission_denied"
EV_WATCH_EVENT = "automation.watch_event"

ALL_AUTOMATION_EVENTS = (
    EV_FILE_CREATED,
    EV_FILE_MODIFIED,
    EV_FILE_DELETED,
    EV_FILE_OPENED,
    EV_FILE_RENAMED,
    EV_FILE_MOVED,
    EV_FILE_COPIED,
    EV_FOLDER_CREATED,
    EV_FOLDER_DELETED,
    EV_BATCH_COMPLETED,
    EV_SCAN_COMPLETED,
    EV_COMMAND_STARTED,
    EV_COMMAND_COMPLETED,
    EV_COMMAND_FAILED,
    EV_PERMISSION_CHECKED,
    EV_PERMISSION_CONFIRMED,
    EV_PERMISSION_DENIED,
    EV_WATCH_EVENT,
)


def emit_automation_event(
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    bus: Any = None,
) -> None:
    """Publish an automation event on the event bus.

    Failures are logged and swallowed so file/command operations remain
    resilient even if a subscriber raises.
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
    except Exception as exc:  # noqa: BLE001 - keep automation path resilient
        logger.warning(f"Failed to emit automation event '{event}': {exc}")
