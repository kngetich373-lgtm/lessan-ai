"""Base class for document format builders."""

from __future__ import annotations

from abc import ABC, abstractmethod

from documents.models import OutputFormat


class FormatBuilder(ABC):
    """Renders a :class:`~documents.formatter.FormattedProject` to a file."""

    output_format: OutputFormat

    @abstractmethod
    def build(self, formatted, path: str) -> str:
        """Render ``formatted`` to ``path``; return the path."""
