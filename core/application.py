"""Application lifecycle facade for Lessan AI.

This module intentionally does not construct the Qt UI or cloud providers.
It provides one safe composition boundary for the executable entry point while
those subsystems are migrated incrementally into the kernel.
"""

from __future__ import annotations

import atexit
import signal
import threading
from typing import Callable, Optional

from core.di.container import Container
from core.kernel import AgentKernel, KernelReport
from core.logging import get_logger

logger = get_logger("LessanApplication")


class LessanApplication:
    """Own the Lessan runtime lifecycle.

    The object is deliberately small: dependency construction belongs in the
    composition root, while this class owns startup/shutdown semantics. This
    prevents UI code and provider adapters from becoming responsible for
    process-wide lifecycle management.
    """

    def __init__(
        self,
        *,
        container: Optional[Container] = None,
        kernel: Optional[AgentKernel] = None,
        install_signal_handlers: bool = False,
    ) -> None:
        self.container = container or Container()
        self.kernel = kernel or AgentKernel(container=self.container)
        self._shutdown_lock = threading.RLock()
        self._shutdown = False
        self._started = False
        self._atexit_registered = False

        if install_signal_handlers:
            self.install_signal_handlers()

    @property
    def started(self) -> bool:
        return self._started and self.kernel.is_ready()

    def start(self) -> KernelReport:
        """Start the runtime exactly once and return the kernel report."""
        with self._shutdown_lock:
            if self.started:
                if self.kernel.last_report is None:
                    raise RuntimeError("Runtime is running without a kernel report")
                return self.kernel.last_report
            report = self.kernel.start()
            self._started = True
            if not self._atexit_registered:
                atexit.register(self.shutdown)
                self._atexit_registered = True
            return report

    def shutdown(self) -> Optional[KernelReport]:
        """Safely shut down the runtime; repeated calls are harmless."""
        with self._shutdown_lock:
            if self._shutdown:
                return self.kernel.last_report
            self._shutdown = True
            try:
                report = self.kernel.shutdown()
            except Exception as exc:  # noqa: BLE001 - shutdown must not escape
                logger.exception("Lessan shutdown failed: %s", exc)
                return None
            finally:
                self._started = False
            return report

    def install_signal_handlers(self) -> None:
        """Arrange graceful shutdown for normal process termination signals."""
        def _handle_signal(signum: int, _frame: object) -> None:
            logger.info("Received signal %s; shutting down Lessan", signum)
            self.shutdown()

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signum, _handle_signal)
            except (ValueError, OSError):
                # Signal handlers can only be installed from the main thread.
                logger.debug("Could not install handler for signal %s", signum)

    def __enter__(self) -> "LessanApplication":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.shutdown()


__all__ = ["LessanApplication"]
