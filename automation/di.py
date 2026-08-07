"""Dependency Injection registration for the File & Command Control System.

Call :func:`register_automation_system` once at application startup (or rely on
the idempotent auto-registration at import time). The subsystem resolves
through the DI container without direct imports elsewhere, and gracefully
degrades when optional cross-subsystem services (Model Router, Memory, State)
are absent — every component works standalone with a fresh policy.
"""

from __future__ import annotations

from typing import Any, Optional

from core.logging import get_logger

logger = get_logger("automation.di")


def register_automation_system(container=None, config=None, event_bus=None):
    """Register all File & Command Control components in the DI container.

    Idempotent — safe to call multiple times. Registers:
      - :class:`~automation.security.SecurityPolicy`
      - :class:`~automation.permissions.PermissionManager`
      - :class:`~automation.file_manager.WorkspaceFileManager`
      - :class:`~automation.command_executor.CommandRegistry`
      - :class:`~automation.command_executor.CommandHistory`
      - :class:`~automation.command_executor.CommandExecutor`
      - :class:`~automation.scanner.WorkspaceScanner`
      - :class:`~automation.watcher.FileWatcher`

    Args:
        container: The DI container (``core.di.Container``).
        config: Optional configuration object (``automation.<key>`` reads).
        event_bus: Optional event bus instance.
    """
    from core.di.container import container as global_container

    from automation.command_executor import (
        CommandExecutor,
        CommandHistory,
        CommandRegistry,
    )
    from automation.file_manager import WorkspaceFileManager
    from automation.permissions import PermissionManager
    from automation.scanner import WorkspaceScanner
    from automation.security import SecurityPolicy
    from automation.watcher import FileWatcher

    container = container or global_container
    if container.has(WorkspaceFileManager):
        return container

    event_bus = _resolve_event_bus(container, event_bus)
    state_store = _resolve_state_store(container)
    memory = _resolve_memory(container)

    policy = container.try_resolve(SecurityPolicy) or SecurityPolicy(config=config)
    permissions = PermissionManager(
        policy, event_bus=event_bus, state_store=state_store, memory=memory
    )
    registry = CommandRegistry()
    history = CommandHistory(capacity=_config_int(config, "max_history", 200))
    file_manager = WorkspaceFileManager(
        permissions,
        event_bus=event_bus,
        state_store=state_store,
        memory=memory,
        default_root=policy.app_root,
        trash_enabled=_config_bool(config, "trash_enabled", True),
    )
    executor = CommandExecutor(
        permissions,
        event_bus=event_bus,
        state_store=state_store,
        memory=memory,
        history=history,
        command_registry=registry,
        default_cwd=policy.app_root,
        default_timeout=_config_float(config, "command_timeout_seconds", 60.0),
        max_output_chars=_config_int(config, "max_output_chars", 100_000),
    )
    scanner = WorkspaceScanner(
        permissions,
        event_bus=event_bus,
        state_store=state_store,
        memory=memory,
        max_read_chars=_config_int(config, "max_file_read_chars", 100_000),
    )
    watcher = FileWatcher(
        permissions,
        event_bus=event_bus,
        state_store=state_store,
        memory=memory,
        interval=_config_float(config, "watch_interval_seconds", 2.0),
    )

    for service, instance in (
        (SecurityPolicy, policy),
        (PermissionManager, permissions),
        (CommandRegistry, registry),
        (CommandHistory, history),
        (WorkspaceFileManager, file_manager),
        (CommandExecutor, executor),
        (WorkspaceScanner, scanner),
        (FileWatcher, watcher),
    ):
        try:
            container.register_instance(service, instance)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not register {service.__name__}: {exc}")

    _mirror_status(state_store, policy)
    logger.info("Registered File & Command Control System in DI container")
    return container


def unregister_automation_system(container) -> None:
    """Remove the automation-system registrations (mainly for tests)."""
    from automation.command_executor import (
        CommandExecutor,
        CommandHistory,
        CommandRegistry,
    )
    from automation.file_manager import WorkspaceFileManager
    from automation.permissions import PermissionManager
    from automation.scanner import WorkspaceScanner
    from automation.security import SecurityPolicy
    from automation.watcher import FileWatcher

    for service in (
        SecurityPolicy,
        PermissionManager,
        CommandRegistry,
        CommandHistory,
        WorkspaceFileManager,
        CommandExecutor,
        WorkspaceScanner,
        FileWatcher,
    ):
        try:
            container.remove(service)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Cross-subsystem resolution (optional, degraded gracefully)
# --------------------------------------------------------------------------- #
def _resolve_event_bus(container, event_bus):
    if event_bus is not None:
        return event_bus
    try:
        from core.event_bus import event_bus as global_event_bus

        return global_event_bus
    except Exception:  # noqa: BLE001
        return None


def _resolve_state_store(container):
    try:
        from core.state import state as global_state

        candidate = container.try_resolve(type(global_state))
        return candidate or global_state
    except Exception:  # noqa: BLE001
        try:
            from core.state.store import StateStore

            return container.try_resolve(StateStore)
        except Exception:  # noqa: BLE001
            return None


def _resolve_memory(container):
    """Resolve the orchestrator MemoryStore adapter; None when unavailable."""
    try:
        from core.orchestrator.interfaces import MemoryStore

        return container.try_resolve(MemoryStore)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Orchestrator MemoryStore not available: {exc}")
    try:
        from memory import MemoryManager

        return container.try_resolve(MemoryManager)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"MemoryManager not available: {exc}")
    return None


def _mirror_status(state_store, policy) -> None:
    """Publish registration status + policy summary into the state store."""
    if state_store is None:
        return
    try:
        state_store.update(
            "automation.status",
            {"registered": True, "policy": policy.as_dict()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Could not mirror automation status: {exc}")


# --------------------------------------------------------------------------- #
# Config helpers (``automation.<key>`` reads, mirroring security._config_value)
# --------------------------------------------------------------------------- #
def _config_value(config: Any, key: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, dict):
        section = config.get("automation") or {}
        return section.get(key, default)
    getter = getattr(config, "get", None)
    if getter is None:
        return default
    try:
        value = getter(f"automation.{key}", None)
    except Exception:  # noqa: BLE001
        return default
    return default if value is None else value


def _config_int(config: Any, key: str, default: int) -> int:
    value = _config_value(config, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_float(config: Any, key: str, default: float) -> float:
    value = _config_value(config, key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _config_bool(config: Any, key: str, default: bool) -> bool:
    value = _config_value(config, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def _auto_register_automation_system() -> None:
    try:
        from core.di.container import container as global_container

        register_automation_system(global_container)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Auto-registration skipped: {exc}")


_auto_register_automation_system()

