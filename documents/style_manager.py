"""Publishing-standard style management for generated documents.

Every builder consumes a resolved :class:`StyleSpec`. The
:class:`StyleManager` starts from the publishing defaults and layers template
overrides and per-request overrides on top, so all formatting rules are
defined in one place:

* Body text: Times New Roman 12pt, 1.5 line spacing, 6pt paragraph gap
* Margins: 1 inch on every side
* Heading hierarchy H1–H4 with distinct sizes, same family
* Title page, running header, centred page-number footer
* Auto-numbered captions for figures and tables

Templates only tweak presentation knobs (colours, spacing, TOC/title page
behaviour) — never content.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional


@dataclass
class StyleSpec:
    """Fully-resolved presentation rules for a document."""

    font_family: str = "Times New Roman"
    mono_family: str = "Courier New"
    base_size: int = 12
    line_spacing: float = 1.5
    space_after_pt: int = 6
    margin_inches: float = 1.0
    title_page: bool = True
    toc_enabled: bool = True
    header_enabled: bool = True
    header_text: Optional[str] = None  # None → the document title
    footer_text: str = "Lessan AI"
    page_numbers: bool = True
    heading_sizes: List[int] = field(default_factory=lambda: [16, 14, 12, 12])
    heading_color: str = "#1F3864"
    heading_bold: bool = True
    caption_italic: bool = True

    def merged(self, other: "StyleSpec") -> "StyleSpec":
        """Return a copy with non-None values from ``other`` applied."""
        updates = {f: getattr(other, f) for f in vars(self) if getattr(other, f) is not None}
        return replace(self, **updates)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_family": self.font_family,
            "mono_family": self.mono_family,
            "base_size": self.base_size,
            "line_spacing": self.line_spacing,
            "space_after_pt": self.space_after_pt,
            "margin_inches": self.margin_inches,
            "title_page": self.title_page,
            "toc_enabled": self.toc_enabled,
            "header_enabled": self.header_enabled,
            "header_text": self.header_text,
            "footer_text": self.footer_text,
            "page_numbers": self.page_numbers,
            "heading_sizes": list(self.heading_sizes),
            "heading_color": self.heading_color,
            "heading_bold": self.heading_bold,
            "caption_italic": self.caption_italic,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "StyleSpec":
        """Build a spec from a partial override dict (request-level)."""
        data = data or {}
        base = cls()
        updates: Dict[str, Any] = {}
        for field_name in vars(base):
            if field_name in data and data[field_name] is not None:
                updates[field_name] = data[field_name]
        return replace(base, **updates)


class StyleManager:
    """Resolves a :class:`StyleSpec` by layering overrides."""

    def __init__(self, defaults: Optional[StyleSpec] = None) -> None:
        self._defaults = defaults or StyleSpec()

    @property
    def defaults(self) -> StyleSpec:
        return self._defaults

    def resolve(
        self,
        template: Any = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> StyleSpec:
        """Resolve the effective spec: defaults → template → request.

        Args:
            template: A :class:`DocumentTemplate` (or any object with a
                ``style`` attribute), or None.
            overrides: Request-level style overrides (e.g. font, spacing,
                TOC/title-page flags).
        """
        spec = self._defaults
        template_style = getattr(template, "style", None)
        if template_style is not None:
            spec = spec.merged(template_style)
        if overrides:
            spec = spec.merged(StyleSpec.from_dict(overrides))
        return spec
