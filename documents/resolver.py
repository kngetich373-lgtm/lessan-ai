"""Resolution of user intent → document type and output formats.

The resolver turns free-form request text ("make a PDF proposal with a table
of contents") into a concrete :class:`DocumentType` and a list of
:class:`OutputFormat` values, using explicit parameters first and natural
language scanning as a fallback.
"""

from __future__ import annotations

import re
from typing import List, Optional

from documents.models import OutputFormat
from documents.types import DocumentType, DocumentTypeRegistry

_FORMAT_KEYWORDS = (
    (re.compile(r"\bpdf\b"), OutputFormat.PDF),
    (re.compile(r"\bdocx\b|\bword\b|\bword document\b"), OutputFormat.DOCX),
    (re.compile(r"\bmarkdown\b|\bmd\b"), OutputFormat.MD),
    (re.compile(r"\bhtml?\b"), OutputFormat.HTML),
    (re.compile(r"\brtf\b|\brich text\b"), OutputFormat.RTF),
    (re.compile(r"\bplain text\b|\btxt\b|\btext file\b"), OutputFormat.TXT),
)


class DocumentResolver:
    """Resolves document kinds and export formats."""

    def __init__(self, registry: Optional[DocumentTypeRegistry] = None) -> None:
        self._registry = registry or DocumentTypeRegistry()

    @property
    def registry(self) -> DocumentTypeRegistry:
        return self._registry

    # ------------------------------------------------------------------ #
    # Kind resolution
    # ------------------------------------------------------------------ #
    def resolve_kind(
        self,
        text: Optional[str] = None,
        explicit: Optional[str] = None,
    ) -> DocumentType:
        """Resolve the document type from an explicit id or free text."""
        if explicit and str(explicit).strip():
            return self._registry.resolve(str(explicit).strip())
        return self._registry.resolve(text)

    # ------------------------------------------------------------------ #
    # Format resolution
    # ------------------------------------------------------------------ #
    def resolve_format(
        self,
        text: Optional[str] = None,
        explicit: Optional[object] = None,
    ) -> List[OutputFormat]:
        """Resolve requested export formats.

        ``explicit`` may be an OutputFormat, a list of them, or a string such
        as ``"pdf"`` or ``"docx, pdf"``. Natural-language mentions in
        ``text`` are detected as a fallback. Defaults to ``[DOCX]``.
        """
        formats: List[OutputFormat] = []
        if explicit not in (None, []):
            if isinstance(explicit, OutputFormat):
                formats.append(explicit)
            elif isinstance(explicit, (list, tuple, set)):
                for item in explicit:
                    if isinstance(item, OutputFormat):
                        formats.append(item)
                    else:
                        try:
                            formats.append(OutputFormat.parse(str(item)))
                        except ValueError:
                            continue
            else:
                for piece in str(explicit).replace(",", " ").split():
                    try:
                        formats.append(OutputFormat.parse(piece))
                    except ValueError:
                        continue

        if not formats:
            haystack = (text or "").lower()
            for pattern, fmt in _FORMAT_KEYWORDS:
                if pattern.search(haystack):
                    formats.append(fmt)

        # De-duplicate while preserving order, defaulting to DOCX.
        seen: List[OutputFormat] = []
        for fmt in formats:
            if fmt not in seen:
                seen.append(fmt)
        return seen or [OutputFormat.DOCX]
