"""Data models for the Professional Document Intelligence System.

Every generated document starts as a single format-agnostic
:class:`DocumentProject` (an *intermediate representation*): a title page
block, an ordered list of :class:`DocumentSection` objects, and typed
elements (paragraphs, bullets, numbered lists, tables, figures, code,
references) inside each section. Each output format is produced by a builder
that walks the same IR, which keeps DOCX, PDF, Markdown, plain text, HTML and
RTF exports consistent with one set of content and one set of style rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class OutputFormat(str, Enum):
    """Supported document export formats."""

    DOCX = "docx"
    PDF = "pdf"
    MD = "md"
    TXT = "txt"
    HTML = "html"
    RTF = "rtf"

    @classmethod
    def parse(cls, value: str) -> "OutputFormat":
        """Parse a loose format string (e.g. ``'.Docx'`` → DOCX)."""
        return cls(str(value).strip().lower().lstrip("."))


@dataclass
class Paragraph:
    """A single body paragraph."""

    text: str
    style: str = "body"  # body | quote | note | small


@dataclass
class Table:
    """A grid table. The first row is a header when ``header_row`` is True."""

    rows: List[List[str]]
    caption: Optional[str] = None
    header_row: bool = True


@dataclass
class Figure:
    """A figure with a caption and an optional image path."""

    caption: str
    path: Optional[str] = None


@dataclass
class CodeBlock:
    """A verbatim code/terminal block."""

    text: str
    language: str = "text"


@dataclass
class DocumentSection:
    """A heading plus the typed elements rendered beneath it."""

    heading: str
    level: int = 1
    paragraphs: List[Paragraph] = field(default_factory=list)
    bullets: List[str] = field(default_factory=list)
    numbered: List[str] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    figures: List[Figure] = field(default_factory=list)
    code_blocks: List[CodeBlock] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    appendix: bool = False
    page_break_after: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentProject:
    """Format-agnostic intermediate representation of a document."""

    kind: str
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    template: Optional[str] = None
    sections: List[DocumentSection] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-friendly dict (workflows, logging)."""
        return {
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "date": self.date,
            "template": self.template,
            "metadata": dict(self.metadata),
            "references": list(self.references),
            "sections": [
                {
                    "heading": s.heading,
                    "level": s.level,
                    "paragraphs": [p.text for p in s.paragraphs],
                    "bullets": list(s.bullets),
                    "numbered": list(s.numbered),
                    "tables": [
                        {
                            "caption": t.caption,
                            "header_row": t.header_row,
                            "rows": [list(r) for r in t.rows],
                        }
                        for t in s.tables
                    ],
                    "figures": [{"caption": f.caption, "path": f.path} for f in s.figures],
                    "code": [{"language": c.language, "text": c.text} for c in s.code_blocks],
                    "references": list(s.references),
                    "appendix": s.appendix,
                    "page_break_after": s.page_break_after,
                }
                for s in self.sections
            ],
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "DocumentProject":
        """Build an IR from an (AI- or workflow-produced) JSON document.

        Tolerant parser: invalid sections are skipped and strings coerced so a
        slightly malformed model payload still yields a usable document.
        """
        data = data or {}
        sections: List[DocumentSection] = []
        for raw in data.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            heading = str(raw.get("heading") or "").strip()
            if not heading:
                continue
            try:
                level = max(1, min(4, int(raw.get("level", 1))))
            except (TypeError, ValueError):
                level = 1

            paragraphs = [
                Paragraph(text=str(t).strip())
                for t in (raw.get("paragraphs") or [])
                if str(t).strip()
            ]
            bullets = [str(b).strip() for b in (raw.get("bullets") or []) if str(b).strip()]
            numbered = [str(n).strip() for n in (raw.get("numbered") or []) if str(n).strip()]

            tables: List[Table] = []
            for t in raw.get("tables") or []:
                if not isinstance(t, dict):
                    continue
                rows = [
                    [str(c) for c in row]
                    for row in (t.get("rows") or [])
                    if isinstance(row, list)
                ]
                if rows:
                    tables.append(
                        Table(
                            rows=rows,
                            caption=t.get("caption"),
                            header_row=bool(t.get("header_row", True)),
                        )
                    )

            figures: List[Figure] = []
            fig = raw.get("figure")
            if isinstance(fig, dict) and str(fig.get("caption") or "").strip():
                figures.append(
                    Figure(caption=str(fig["caption"]).strip(), path=fig.get("path"))
                )

            code_blocks: List[CodeBlock] = []
            code = raw.get("code")
            if isinstance(code, dict) and str(code.get("text") or "").strip():
                code_blocks.append(
                    CodeBlock(text=str(code["text"]), language=str(code.get("language") or "text"))
                )

            references = [str(r).strip() for r in (raw.get("references") or []) if str(r).strip()]

            sections.append(
                DocumentSection(
                    heading=heading,
                    level=level,
                    paragraphs=paragraphs,
                    bullets=bullets,
                    numbered=numbered,
                    tables=tables,
                    figures=figures,
                    code_blocks=code_blocks,
                    references=references,
                    appendix=bool(raw.get("appendix", False)),
                    page_break_after=bool(raw.get("page_break_after", False)),
                )
            )

        references = [str(r).strip() for r in (data.get("references") or []) if str(r).strip()]
        metadata: Dict[str, Any] = {}
        raw_meta = data.get("metadata") or {}
        if isinstance(raw_meta, dict):
            for k, v in raw_meta.items():
                if v is None or isinstance(v, (str, int, float, bool)):
                    metadata[k] = v

        title = str(data.get("title") or "Untitled Document").strip() or "Untitled Document"
        return cls(
            kind=str(data.get("kind") or "report"),
            title=title,
            subtitle=data.get("subtitle") or None,
            author=data.get("author") or None,
            date=data.get("date") or None,
            template=data.get("template") or None,
            sections=sections,
            references=references,
            metadata=metadata,
        )


@dataclass
class DocumentRequest:
    """User-facing request passed to the :class:`DocumentGenerator`."""

    document_type: Optional[str] = None
    topic: Optional[str] = None
    content: Optional[str] = None
    instructions: Optional[str] = None
    formats: List[OutputFormat] = field(default_factory=lambda: [OutputFormat.DOCX])
    template: Optional[str] = None
    output_name: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    font_family: Optional[str] = None
    line_spacing: Optional[float] = None
    toc: Optional[bool] = None
    title_page: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """All free-form text, used for natural-language resolution."""
        return " ".join(
            p for p in (self.topic, self.content, self.instructions) if p
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON-friendly serialisation for workflow step parameters."""
        return {
            "document_type": self.document_type,
            "topic": self.topic,
            "content": self.content,
            "instructions": self.instructions,
            "formats": [f.value for f in self.formats],
            "template": self.template,
            "output_name": self.output_name,
            "author": self.author,
            "date": self.date,
            "font_family": self.font_family,
            "line_spacing": self.line_spacing,
            "toc": self.toc,
            "title_page": self.title_page,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "DocumentRequest":
        """Build a request from a tool-parameter dict (main.py/agent)."""
        data = data or {}

        formats: List[OutputFormat] = []
        raw_formats = data.get("formats") or data.get("format")
        if raw_formats is None:
            formats = [OutputFormat.DOCX]
        elif isinstance(raw_formats, (list, tuple, set)):
            for f in raw_formats:
                try:
                    formats.append(OutputFormat.parse(str(f)))
                except ValueError:
                    continue
        else:
            for piece in str(raw_formats).replace(",", " ").split():
                try:
                    formats.append(OutputFormat.parse(piece))
                except ValueError:
                    continue
        if not formats:
            formats = [OutputFormat.DOCX]

        def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        return cls(
            document_type=data.get("document_type") or data.get("type"),
            topic=data.get("topic"),
            content=data.get("content"),
            instructions=data.get("instructions"),
            formats=formats,
            template=data.get("template"),
            output_name=data.get("output_name"),
            author=data.get("author"),
            date=data.get("date"),
            font_family=data.get("font_family") or data.get("font"),
            line_spacing=_float(data.get("line_spacing")),
            toc=data.get("toc") if isinstance(data.get("toc"), bool) else None,
            title_page=data.get("title_page") if isinstance(data.get("title_page"), bool) else None,
            metadata=data.get("metadata") or {},
        )


@dataclass
class DocumentResult:
    """Outcome of a generation run."""

    request: DocumentRequest
    kind: str
    template: str
    title: str
    paths: Dict[OutputFormat, str]
    generated_from: str = "template"  # "ai" | "skeleton"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def primary_path(self) -> Optional[str]:
        """Return the most useful export path (DOCX first, then PDF…)."""
        for fmt in (OutputFormat.DOCX, OutputFormat.PDF, OutputFormat.HTML,
                    OutputFormat.RTF, OutputFormat.MD, OutputFormat.TXT):
            if fmt in self.paths:
                return self.paths[fmt]
        return next(iter(self.paths.values()), None)

    def summary(self) -> str:
        lines = [f"Generated document: {self.title}"]
        lines.append(
            f"  Type: {self.kind} · Template: {self.template} · Content: {self.generated_from}"
        )
        for fmt, path in self.paths.items():
            lines.append(f"  {fmt.value.upper()}: {path}")
        return "\n".join(lines)


def today_str() -> str:
    """Publishing-style date string (e.g. ``August 7, 2026``)."""
    return datetime.now().strftime("%B %d, %Y")


