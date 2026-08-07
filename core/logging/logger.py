"""Structured logging framework for Lessan AI."""

import json
import logging
import sys
import threading
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Optional


class LogLevel(IntEnum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Logger:
    """Thin structured logging wrapper around the standard library."""

    def __init__(self, name: str, logger: logging.Logger):
        self._name = name
        self._logger = logger

    @property
    def name(self) -> str:
        return self._name

    def debug(self, message: str, **context: Any) -> None:
        self._log(logging.DEBUG, message, context)

    def info(self, message: str, **context: Any) -> None:
        self._log(logging.INFO, message, context)

    def warning(self, message: str, **context: Any) -> None:
        self._log(logging.WARNING, message, context)

    def error(self, message: str, **context: Any) -> None:
        self._log(logging.ERROR, message, context)

    def critical(self, message: str, **context: Any) -> None:
        self._log(logging.CRITICAL, message, context)

    def _log(self, level: int, message: str, context: Dict[str, Any]) -> None:
        if context:
            context_str = json.dumps(context, ensure_ascii=False, default=str)
            self._logger.log(level, f"{message} {context_str}")
        else:
            self._logger.log(level, message)


class _StructuredFormatter(logging.Formatter):
    """Formatter that adds a timestamp and structured JSON context."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        base = f"[{ts}] [{record.levelname}] [{record.name}] {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


_loggers: Dict[str, Logger] = {}
_loggers_lock = threading.Lock()
_configured = False


def configure_logging(
    level: LogLevel = LogLevel.INFO,
    log_file: Optional[Path] = None,
    console: bool = True,
) -> None:
    """Configure the root logging handler(s). Safe to call multiple times."""
    global _configured

    root = logging.getLogger()
    root.setLevel(level.value)

    # Remove existing handlers to avoid duplicates
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = _StructuredFormatter()

    if console:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> Logger:
    """Get (or create) a structured logger for the given module name."""
    with _loggers_lock:
        if name in _loggers:
            return _loggers[name]
        logger = Logger(name, logging.getLogger(name))
        _loggers[name] = logger
        return logger