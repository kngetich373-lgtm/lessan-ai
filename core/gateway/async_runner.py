"""Background async loop runner — safely calls async code from sync callers.

Provides a single shared event loop running in a daemon thread so that
synchronous gateway methods (``GatewayManager.connect``,
``GatewayHub.chat``, etc.) can invoke async adapter methods without
``RuntimeError: This event loop is already running`` — a common issue
on Python 3.13+ when called from within an already-running loop.
"""

import asyncio
import threading
from typing import Any


class BackgroundLoop:
    """A dedicated event loop running in a daemon thread.

    ``run(coro)`` submits *coro* to the background loop and blocks
    until it completes, returning the result.  ``create_task(coro)``
    submits without waiting and returns a ``concurrent.futures.Future``.
    """

    _instance: "BackgroundLoop | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def get(cls) -> "BackgroundLoop":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance._start()
            return cls._instance

    def _start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="gateway-bg-loop", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro):
        """Submit *coro* and block until it completes. Returns the result."""
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def stop(self) -> None:
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=2)
            self._loop = None
            self._thread = None


def run_async(coro):
    """Convenience: run a coroutine on the shared background loop."""
    return BackgroundLoop.get().run(coro)
