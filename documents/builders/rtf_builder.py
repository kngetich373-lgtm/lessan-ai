"""RTF builder — hand-crafted RTF 1.0 output (no third-party dependency).

Generates a standards-compliant RTF file with a font table, colour table,
page margins, a running footer with page numbers, numbered headings, body
text, bullets, numbered lists, tables (simple cell borders), figure captions,
code blocks and references.
"""

from __future__ import annotations

from typing import List

from documents.builders.base import FormatBuilder
from documents.models import OutputFormat


def _esc(text: str) -> str:
    """Escape characters that are special in RTF."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("\n", "\\line ")
    return text


def _heading_size_pt(level: int, sizes) -> int:
    s = sizes[min(level - 1, len(sizes) - 1)] if sizes else 16
    return s * 2  # RTF font sizes are in half-points


def _line_spacing(hundredths: float) -> int:
    """Return the \\sl value (twips) for 12pt body line spacing."""
    return int(240 * hundredths)


class RTFBuilder(FormatBuilder):
    """Exports the document as a standard RTF file."""

    output_format = OutputFormat.RTF

    def build(self, formatted, path: str) -> str:
        style = formatted.style
        parts: List[str] = [
            r"{\rtf1\ansi\deff0",
            _font_table(style),
            _colour_table(style),
            _page_margins(style.margin_inches),
        ]
        if style.header_enabled:
            header_text = style.header_text or formatted.title
            parts.append(r"{\header\pard\qr\fs18 " + _esc(header_text) + r"\par}")
        if style.footer_text:
            footer = r"{\footer\pard\qc\fs18 " + _esc(style.footer_text)
            if style.page_numbers:
                footer += r"   Page  \chpgn"
            footer += r"\par}"
            parts.append(footer)

        if formatted.title_page:
            _add_title_page(parts, formatted, style)
        if formatted.toc:
            _add_toc(parts, formatted, style)

        for section in formatted.project.sections:
            _add_section(parts, section, style)

        parts.append("}")
        text = "\n".join(parts)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


def _font_table(style) -> str:
    return (
        r"{\fonttbl"
        r"{\f0 " + style.font_family + r";}"
        r"{\f1 " + style.mono_family + r";}}"
    )


def _colour_table(style) -> str:
    hex_c = str(style.heading_color).lstrip("#")
    try:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 31, 56, 100
    return r"{\colortbl;\red" + str(r) + r"\green" + str(g) + r"\blue" + str(b) + ";}"


def _page_margins(margin_inches: float) -> str:
    twips = int(margin_inches * 1440)
    return f"\\margl{twips}\\margr{twips}\\margt{twips}\\margb{twips}"


def _add_title_page(parts: List, formatted, style) -> None:
    parts.append(r"{\pard\qc\fs56\b " + _esc(formatted.title) + r"\par}")
    if formatted.subtitle:
        parts.append(r"{\pard\qc\fs32\i " + _esc(formatted.subtitle) + r"\par}")
    parts.append(r"{\pard\qc\sa480 \par}")
    if formatted.author:
        parts.append(r"{\pard\qc\fs28 " + _esc(formatted.author) + r"\par}")
    parts.append(r"{\pard\qc\fs24 " + _esc(formatted.date) + r"\par}")
    parts.append(r"\newpage")


def _add_toc(parts: List, formatted, style) -> None:
    parts.append(r"{\pard\sa240\qc\b\fs32 Table of Contents\par}")
    for entry in formatted.toc_entries:
        indent = (entry.level - 1) * 360
        parts.append(
            rf"{{\pard\sl360\slmult1\sa120\li{indent}"
            + _esc(entry.label)
            + r"\par}"
        )
    parts.append(r"\newpage")


def _add_section(parts: List, section, style) -> None:
    number = section.meta.get("number", "")
    heading_text = f"{number}  {section.heading}".strip()
    hsize = _heading_size_pt(section.level, style.heading_sizes)
    parts.append(
        rf"{{\pard\sb240\sa120\fs{hsize}\cf1\b {_esc(heading_text)}\par}}"
    )
    sl = _line_spacing(style.line_spacing)
    body_size = style.base_size * 2
    for p in section.paragraphs:
        parts.append(
            rf"{{\pard\sl{sl}\slmult1\sa{style.space_after_pt}\fs{body_size} {_esc(p.text)}\par}}"
        )
    for item in section.bullets:
        parts.append(
            rf"{{\pard\sl{sl}\slmult1\sa{style.space_after_pt}\fs{body_size}"
            rf"\li720 -\tab {_esc(item)}\par}}"
        )
    for index, item in enumerate(section.numbered, start=1):
        parts.append(
            rf"{{\pard\sl{sl}\slmult1\sa{style.space_after_pt}\fs{body_size}"
            rf"\li720 {index}.\tab {_esc(item)}\par}}"
        )
    for table in section.tables:
        _add_table(parts, table, style)
    for figure in section.figures:
        parts.append(
            rf"{{\pard\qc\i\fs{body_size - 2} {_esc(figure.caption)}\par}}"
        )
    for code_block in section.code_blocks:
        parts.append(r"{\pard\fs20\f1 ")
        parts.append(_esc(code_block.text))
        parts.append(r"\par}")
    for reference in section.references:
        parts.append(
            rf"{{\pard\sl360\slmult1\sa120\li720\fi-360\fs{body_size - 2} {_esc(reference)}\par}}"
        )
    if section.page_break_after:
        parts.append(r"\page")


def _add_table(parts: List, table, style) -> None:
    rows = table.rows
    if not rows:
        return
    if table.caption:
        parts.append(
            rf"{{\pard\qc\i\fs{style.base_size * 2 - 2} {_esc(table.caption)}\par}}"
        )
    col_count = max(len(r) for r in rows)
    page_width = 9360  # letter width minus 2×1″ margins, in twips
    col_width = page_width // col_count
    for ri, row in enumerate(rows):
        parts.append(r"\trowd\trgaph108\trleft-50")
        for ci in range(col_count):
            right = (ci + 1) * col_width
            parts.append(
                r"\clbrdrt\brdrs\clbrdrl\brdrs\clbrdrb\brdrs\clbrdrr\brdrs\cellx"
                + str(right)
            )
        parts.append(r"\intbl")
        for ci in range(col_count):
            cell_text = row[ci] if ci < len(row) else ""
            bold = r"\b " if (ri == 0 and table.header_row) else ""
            parts.append(r"{" + bold + _esc(cell_text) + r"}\cell")
        parts.append(r"\row")
    parts.append(r"\pard\sa120")


