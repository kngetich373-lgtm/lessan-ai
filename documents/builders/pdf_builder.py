"""PDF builder — publishing-standard PDF export via ReportLab.

Produces a letter-size PDF with 1-inch margins, a separate title page, a
dot-leader table of contents (page numbers via ``multiBuild``), running
header, centred page-number footer (restarting after the title page), and
auto-numbered captions. Times family is used by default; fonts are mapped
from the resolved :class:`StyleSpec`.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from core.logging import get_logger

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from documents.builders.base import FormatBuilder
from documents.models import OutputFormat

logger = get_logger("documents.pdf")

_FONT_ALIASES = {
    "times new roman": "Times-Roman",
    "times": "Times-Roman",
    "garamond": "Times-Roman",
    "georgia": "Times-Roman",
    "helvetica": "Helvetica",
    "arial": "Helvetica",
    "calibri": "Helvetica",
    "courier new": "Courier",
    "courier": "Courier",
    "consolas": "Courier",
}

_VARIANT_NAMES = {
    "Times-Roman": {
        "bold": "Times-Bold",
        "italic": "Times-Italic",
        "both": "Times-BoldItalic",
    },
    "Helvetica": {
        "bold": "Helvetica-Bold",
        "italic": "Helvetica-Oblique",
        "both": "Helvetica-BoldOblique",
    },
    "Courier": {
        "bold": "Courier-Bold",
        "italic": "Courier-Oblique",
        "both": "Courier-BoldOblique",
    },
}


def _font_family(style, mono: bool = False) -> str:
    family = style.mono_family if mono else style.font_family
    return _FONT_ALIASES.get(str(family).strip().lower(), "Times-Roman")


def _font_variant(family: str, *, bold: bool = False, italic: bool = False) -> str:
    """Return a registered reportlab base-14 font name for the variant."""
    table = _VARIANT_NAMES.get(family)
    if table is None:
        return family
    if bold and italic:
        return table["both"]
    if bold:
        return table["bold"]
    if italic:
        return table["italic"]
    return family



class _DocumentTemplate(BaseDocTemplate):
    """Letter template with a bare title page and a body page template."""

    def __init__(self, filename: str, title_text: str, footer_text: str, style) -> None:
        self._title_text = title_text
        self._footer_text = footer_text
        self._font = _font_family(style)
        super().__init__(
            filename,
            pagesize=letter,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
        )
        self._toc = TableOfContents()
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="main")
        self.addPageTemplates(
            [
                PageTemplate(id="title", frames=[frame], onPage=self._title_page),
                PageTemplate(id="body", frames=[frame], onPage=self._body_page),
            ]
        )

    # -- TOC collection ------------------------------------------------- #
    def afterFlowable(self, flowable) -> None:  # noqa: N802 (reportlab API)
        if isinstance(flowable, Paragraph):
            entry = getattr(flowable, "_toc_entry", None)
            if entry:
                level, text = entry
                self.notify("TOCEntry", (level, text, self.page))

    # -- page decoration ------------------------------------------------- #
    def _title_page(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.restoreState()

    def _body_page(self, canvas, doc) -> None:
        canvas.saveState()
        page_width, page_height = self.pagesize
        font = self._font
        if self._title_text:
            canvas.setFont(_font_variant(font, bold=False), 9)
            canvas.setFillColor(colors.HexColor("#666666"))
            canvas.drawRightString(
                page_width - inch, page_height - 0.6 * inch, self._title_text
            )
        if self._footer_text:
            canvas.setFont(_font_variant(font, bold=False), 10)
            canvas.setFillColor(colors.black)
            canvas.drawCentredString(page_width / 2.0, 0.55 * inch, self._footer_text)
        # Body starts on physical page 2 → show page 1.
        canvas.drawCentredString(page_width / 2.0, 0.4 * inch, str(max(doc.page - 1, 1)))
        canvas.restoreState()


class PdfBuilder(FormatBuilder):
    """Exports the document as a professional PDF file."""

    output_format = OutputFormat.PDF

    def build(self, formatted, path: str) -> str:
        style = formatted.style
        doc = _DocumentTemplate(path, formatted.title, style.footer_text, style)

        story: List = []
        if formatted.title_page:
            self._render_title_page(story, formatted, style)
        if formatted.toc:
            self._render_toc(story, formatted, style, doc)
        for section in formatted.project.sections:
            self._render_section(story, section, formatted, style)


        # Page numbers need a second pass → multiBuild; fall back gracefully.
        try:
            doc.multiBuild(story)
        except Exception as exc:  # noqa: BLE001 - degrade to single pass
            logger.warning(f"PDF multiBuild failed ({exc}); falling back to single pass")
            fallback = [flowable for flowable in story if not isinstance(flowable, TableOfContents)]
            doc.build(fallback)

        return path

    # ------------------------------------------------------------------ #
    # Render helpers
    # ------------------------------------------------------------------ #
    def _render_title_page(self, story: List, formatted, style) -> None:
        font = _font_family(style)
        story.append(Spacer(1, 2.2 * inch))
        title_style = ParagraphStyle(
            "doc-title",
            fontName=_font_variant(font, bold=True),
            fontSize=26,
            leading=32,
            alignment=TA_CENTER,
            textColor=_hex_color(style.heading_color),
        )
        story.append(Paragraph(formatted.title, title_style))
        if formatted.subtitle:
            subtitle_style = ParagraphStyle(
                "doc-subtitle",
                fontName=_font_variant(font, italic=True),
                fontSize=15,
                leading=19,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#444444"),
            )
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(formatted.subtitle, subtitle_style))
        story.append(Spacer(1, 1.6 * inch))
        for line in (formatted.author, formatted.date):
            if line:
                meta_style = ParagraphStyle(
                    "doc-meta",
                    fontName=_font_variant(font),
                    fontSize=12,
                    leading=16,
                    alignment=TA_CENTER,
                )
                story.append(Paragraph(line, meta_style))
        story.append(NextPageTemplate("body"))
        story.append(PageBreak())

    def _render_toc(self, story: List, formatted, style, doc) -> None:
        font = _font_family(style)
        toc_title = ParagraphStyle(
            "toc-title",
            fontName=_font_variant(font, bold=True),
            fontSize=_heading_size(style, 1),
            leading=22,
            spaceAfter=14,
            textColor=_hex_color(style.heading_color),
        )
        story.append(Paragraph("Table of Contents", toc_title))
        toc = doc._toc
        toc.levelStyles = [
            ParagraphStyle(
                "toc1",
                fontName=_font_variant(font, bold=True),
                fontSize=11,
                leading=16,
                spaceBefore=2,
            ),
            ParagraphStyle(
                "toc2",
                fontName=_font_variant(font),
                fontSize=11,
                leading=15,
                leftIndent=14,
            ),
            ParagraphStyle(
                "toc3",
                fontName=_font_variant(font, italic=True),
                fontSize=11,
                leading=15,
                leftIndent=28,
            ),
        ]
        toc.dotsMinLevel = 0
        story.append(toc)
        story.append(PageBreak())

    def _render_section(self, story: List, section, formatted, style) -> None:
        font = _font_family(style)
        level = min(4, section.level)
        number = section.meta.get("number", "")
        heading_text = f"{number}  {section.heading}".strip()
        heading_style = ParagraphStyle(
            f"doc-heading-{level}",
            fontName=_font_variant(font, bold=style.heading_bold),
            fontSize=_heading_size(style, level),
            leading=_heading_size(style, level) * 1.25,
            spaceBefore=18 if level == 1 else 12,
            spaceAfter=8,
            keepWithNext=True,
            textColor=_hex_color(style.heading_color),
        )
        heading_para = Paragraph(heading_text, heading_style)
        heading_para._toc_entry = (level, heading_text)
        story.append(heading_para)

        body_style = ParagraphStyle(
            "doc-body",
            fontName=_font_variant(font),
            fontSize=style.base_size,
            leading=style.base_size * style.line_spacing,
            spaceAfter=style.space_after_pt,
            alignment=TA_LEFT,
        )

        for paragraph in section.paragraphs:
            para_style = body_style
            if paragraph.style == "quote":
                para_style = ParagraphStyle(
                    "doc-quote",
                    parent=body_style,
                    leftIndent=18,
                    fontName=_font_variant(font, italic=True),
                )
            elif paragraph.style == "small":
                para_style = ParagraphStyle(
                    "doc-small", parent=body_style, fontSize=style.base_size - 1
                )
            story.append(Paragraph(paragraph.text, para_style))

        for item in section.bullets:
            bullet_style = ParagraphStyle(
                "doc-bullet",
                parent=body_style,
                leftIndent=18,
                bulletIndent=0,
            )
            story.append(Paragraph(item, bullet_style, bulletText="\u2022"))

        for index, item in enumerate(section.numbered, start=1):
            numbered_style = ParagraphStyle(
                "doc-numbered",
                parent=body_style,
                leftIndent=24,
                bulletIndent=0,
            )
            story.append(Paragraph(item, numbered_style, bulletText=f"{index}."))

        for table in section.tables:
            self._render_table(story, table, formatted, style)

        for figure in section.figures:
            self._render_figure(story, figure, formatted, style)

        for code_block in section.code_blocks:
            self._render_code(story, code_block, formatted, style)

        for reference in section.references:
            reference_style = ParagraphStyle(
                "doc-reference",
                parent=body_style,
                fontSize=style.base_size - 1,
                leftIndent=24,
                firstLineIndent=-12,
            )
            story.append(Paragraph(reference, reference_style))

        if section.page_break_after:
            story.append(PageBreak())

    def _render_table(self, story: List, table, formatted, style) -> None:
        font = _font_family(style)
        if table.caption:
            caption_style = ParagraphStyle(
                "doc-caption",
                fontName=_font_variant(font, italic=style.caption_italic),
                fontSize=style.base_size - 1,
                leading=14,
                alignment=TA_CENTER,
                spaceBefore=6,
                spaceAfter=4,
            )
            story.append(Paragraph(table.caption, caption_style))

        rows = table.rows
        if not rows:
            return
        column_count = max(len(row) for row in rows)
        data = []
        for row_index, row in enumerate(rows):
            cells = []
            for col_index in range(column_count):
                text = row[col_index] if col_index < len(row) else ""
                cell_style = ParagraphStyle(
                    f"cell-{row_index}-{col_index}",
                    fontName=_font_variant(font, bold=(row_index == 0 and table.header_row)),
                    fontSize=style.base_size - 1,
                    leading=style.base_size * 1.15,
                    spaceBefore=2,
                    spaceAfter=2,
                )
                cells.append(Paragraph(text, cell_style))
            data.append(cells)

        table_flowable = Table(data, hAlign="LEFT")
        style_commands = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if table.header_row and data:
            style_commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF5")))
        table_flowable.setStyle(TableStyle(style_commands))
        story.append(table_flowable)
        story.append(Spacer(1, style.space_after_pt))

    def _render_figure(self, story: List, figure, formatted, style) -> None:
        font = _font_family(style)
        if figure.path and os.path.exists(str(figure.path)):
            try:
                story.append(Image(str(figure.path), width=5.5 * inch, height=4 * inch))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Could not embed figure image {figure.path}: {exc}")
        caption_style = ParagraphStyle(
            "doc-figure-caption",
            fontName=_font_variant(font, italic=style.caption_italic),
            fontSize=style.base_size - 1,
            leading=14,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=8,
        )
        story.append(Paragraph(figure.caption, caption_style))

    def _render_code(self, story: List, code_block, formatted, style) -> None:
        mono = _font_family(style, mono=True)
        code_style = ParagraphStyle(
            "doc-code",
            fontName=mono,
            fontSize=style.base_size - 1,
            leading=style.base_size * 1.1,
            leftIndent=6,
            rightIndent=6,
            spaceBefore=6,
            spaceAfter=6,
        )
        wrapper = Table(
            [[Preformatted(code_block.text, code_style)]],
            colWidths=[letter[0] - 2 * inch],
            hAlign="LEFT",
        )
        wrapper.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F5F5")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(wrapper)
        story.append(Spacer(1, style.space_after_pt))


def _hex_color(value: str) -> colors.HexColor:
    try:
        return colors.HexColor(str(value).lstrip("#"))
    except (TypeError, ValueError):
        return colors.HexColor("#1F3864")


def _heading_size(style, level: int) -> int:
    sizes = getattr(style, "heading_sizes", None) or [16, 14, 12, 12]
    return sizes[min(level - 1, len(sizes) - 1)]




