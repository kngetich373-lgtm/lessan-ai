"""Export orchestration for the Professional Document Intelligence System.

:class:`ExportManager` routes a formatted document to the registered
:class:`FormatBuilder` for every requested output format, writing into
``~/Lessan/reports/documents`` (matching the convention used by other Lessan
actions). Unknown formats are skipped with a warning so one missing exporter
never blocks the others.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.logging import get_logger

from documents.models import OutputFormat

logger = get_logger("documents.exporters")

_DEFAULT_OUTPUT_DIR = Path.home() / "Lessan" / "reports" / "documents"


class ExportManager:
    """Registers format builders and renders documents to disk."""

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._builders: Dict[OutputFormat, object] = {}
        self._output_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
        self._register_builtins()

    def _register_builtins(self) -> None:
        from documents.builders import builtin_builders

        for builder_cls in builtin_builders:
            try:
                self.register(builder_cls())
            except Exception as exc:  # noqa: BLE001 - optional exporter
                logger.warning(f"Could not initialise {builder_cls.__name__}: {exc}")

    # ------------------------------------------------------------------ #
    # Registration / introspection
    # ------------------------------------------------------------------ #
    def register(self, builder: object) -> None:
        output_format = getattr(builder, "output_format", None)
        if output_format is None or not isinstance(output_format, OutputFormat):
            raise ValueError(f"Builder {type(builder).__name__} has no output_format")
        self._builders[output_format] = builder

    def supports(self, fmt: OutputFormat) -> bool:
        return fmt in self._builders

    @property
    def formats(self) -> List[OutputFormat]:
        return list(self._builders)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def export(
        self,
        formatted: object,
        fmt: OutputFormat,
        output_name: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        """Render ``formatted`` in ``fmt`` and return the output path."""
        builder = self._builders.get(fmt)
        if builder is None:
            raise ValueError(
                f"No builder registered for format '{fmt.value}'. "
                f"Available: {[f.value for f in self._builders]}"
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _slugify(output_name) or _slugify(
            getattr(formatted, "title", None) or getattr(formatted, "kind", "document")
        )
        path = self._output_dir / f"{base}_{stamp}.{fmt.value}"
        result = builder.build(formatted, str(path))
        logger.info(f"Exported {fmt.value.upper()} → {result}")
        return result


def open_file(path: str) -> None:
    """Open a generated file in the platform's default viewer."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not auto-open {path}: {exc}")


def _slugify(value: Optional[str]) -> str:
    if not value:
        return "document"
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "document"
