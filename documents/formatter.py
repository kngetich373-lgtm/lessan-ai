"""Formatting pass: turn a raw :class:`DocumentProject` into the
fully-presentable :class:`FormattedProject` every builder consumes.

Responsibilities:
  * Layering style defaults → template → request overrides
  * Numbering headings (1 / 1.1 / 1.1.1) and appendices (Appendix A, B, …)
  * Auto-numbering figure/table captions ("Figure 1:", "Table 2:")
  * Collecting table-of-contents entries (levels 1–3)
  * Normalising title, author and date for the title page
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from documents.models import DocumentProject, DocumentSection, today_str
from documents.style_manager import StyleManager, StyleSpec


@dataclass
class TOCEntry:
    """A table-of-contents line."""

    level: int
    number: str
    heading: str

    @property
    def label(self) -> str:
        return f"{self.number}  {self.heading}".strip()


@dataclass
class FormattedProject:
    """A document prepared for export."""

    project: DocumentProject
    style: StyleSpec
    toc_entries: List[TOCEntry] = field(default_factory=list)
    figure_count: int = 0
    table_count: int = 0
    toc: bool = False
    title_page: bool = True
    title: str = ""
    subtitle: Optional[str] = None
    author: Optional[str] = None
    date: str = ""
    has_references: bool = False


class DocumentFormatter:
    """Applies publishing formatting rules to a project."""

    def __init__(self, style_manager: Optional[StyleManager] = None) -> None:
        self._styles = style_manager or StyleManager()

    def format(
        self,
        project: DocumentProject,
        template: Any = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> FormattedProject:
        style = self._styles.resolve(template, overrides)

        toc_entries: List[TOCEntry] = []
        counters = [0, 0, 0, 0]
        appendix_count = 0
        figure_count = 0
        table_count = 0

        for section in project.sections:
            level = max(1, min(4, section.level))
            if section.appendix and level == 1:
                appendix_count += 1
                number = f"Appendix {chr(ord('A') + appendix_count - 1)}"
            else:
                counters[level - 1] += 1
                for idx in range(level, 4):
                    counters[idx] = 0
                number = ".".join(str(c) for c in counters[:level])
            section.meta["number"] = number

            if level <= 3 and not section.appendix:
                toc_entries.append(TOCEntry(level=level, number=number, heading=section.heading))

            for table in section.tables:
                if table.caption:
                    table_count += 1
                    table.caption = f"Table {table_count}: {table.caption}"
            for figure in section.figures:
                figure_count += 1
                figure.caption = f"Figure {figure_count}: {figure.caption}"

        # Global references: ensure they surface in a section so every builder
        # (including DOCX/PDF/RTF, which render per-section) prints them.
        if project.references:
            ref_section = next(
                (
                    s
                    for s in project.sections
                    if s.heading.strip().lower().startswith("reference") and s.level == 1
                ),
                None,
            )
            if ref_section is not None:
                ref_section.references = list(dict.fromkeys(list(ref_section.references) + list(project.references)))
            else:
                ref_section = DocumentSection(heading="References", level=1)
                ref_section.references = list(dict.fromkeys(project.references))
                project.sections.append(ref_section)
                counters[0] += 1
                ref_section.meta["number"] = str(counters[0])
                toc_entries.append(
                    TOCEntry(level=1, number=str(counters[0]), heading="References")
                )

        toc_enabled = bool(style.toc_enabled and len(toc_entries) >= 2)
        has_references = bool(
            project.references
            or any(section.references for section in project.sections)
        )

        return FormattedProject(
            project=project,
            style=style,
            toc_entries=toc_entries,
            figure_count=figure_count,
            table_count=table_count,
            toc=toc_enabled,
            title_page=bool(style.title_page),
            title=project.title or "Untitled Document",
            subtitle=project.subtitle,
            author=project.author or "Lessan AI",
            date=project.date or today_str(),
            has_references=has_references,
        )
