"""Plain-text builder — monospaced, aligned, printer-friendly export."""

from __future__ import annotations

import textwrap
from typing import List

from documents.builders.base import FormatBuilder
from documents.models import OutputFormat

_WIDTH = 100


class TextBuilder(FormatBuilder):
    """Exports the document as plain text with a professional layout."""

    output_format = OutputFormat.TXT

    def build(self, formatted, path: str) -> str:
        style = formatted.style
        lines: List[str] = []

        # Title page
        lines.append(formatted.title.upper().center(_WIDTH))
        lines.append("=" * len(formatted.title))
        lines.append("")
        if formatted.subtitle:
            lines.append(formatted.subtitle.center(_WIDTH))
            lines.append("")
        lines.append("")
        lines.append(f"Author: {formatted.author}".center(_WIDTH))
        lines.append(f"Date:   {formatted.date}".center(_WIDTH))
        lines.append("")
        lines.append("=" * _WIDTH)
        lines.append("")

        if formatted.toc:
            lines.append("TABLE OF CONTENTS".center(_WIDTH))
            lines.append("-" * _WIDTH)
            for entry in formatted.toc_entries:
                indent = "  " * (entry.level - 1)
                lines.append(f"{indent}{entry.label}")
            lines.append("")
            lines.append("=" * _WIDTH)
            lines.append("")

        for section in formatted.project.sections:
            number = section.meta.get("number", "")
            heading = f"{number}  {section.heading}".strip()
            lines.append(heading)
            lines.append("-" * len(heading))
            lines.append("")

            for paragraph in section.paragraphs:
                for wrapped in textwrap.wrap(paragraph.text, _WIDTH):
                    lines.append(wrapped)
                lines.append("")

            for item in section.bullets:
                bullet_lines = textwrap.wrap(item, _WIDTH - 4)
                if bullet_lines:
                    lines.append(f"  - {bullet_lines[0]}")
                    for continuation in bullet_lines[1:]:
                        lines.append(f"    {continuation}")
            if section.bullets:
                lines.append("")

            for index, item in enumerate(section.numbered, start=1):
                numbered_lines = textwrap.wrap(item, _WIDTH - 4)
                lines.append(f"  {index}. {numbered_lines[0]}" if numbered_lines else "")
                for continuation in numbered_lines[1:]:
                    lines.append(f"      {continuation}")
            if section.numbered:
                lines.append("")

            for table in section.tables:
                lines.extend(_text_table(table.rows))
                if table.caption:
                    lines.append(f"{table.caption}".center(_WIDTH))
                lines.append("")

            for figure in section.figures:
                lines.append(figure.caption.center(_WIDTH))
                lines.append("")

            for code_block in section.code_blocks:
                lines.append("_" * _WIDTH)
                for line in code_block.text.splitlines():
                    lines.append(line)
                lines.append("_" * _WIDTH)
                lines.append("")

            for reference in section.references:
                for wrapped in textwrap.wrap(reference, _WIDTH - 2):
                    lines.append(f"  {wrapped}")
            if section.references:
                lines.append("")

        if formatted.project.references and not any(
            s.references for s in formatted.project.sections
        ):
            lines.append("REFERENCES")
            lines.append("=" * _WIDTH)
            for index, reference in enumerate(formatted.project.references, start=1):
                ref_lines = textwrap.wrap(reference, _WIDTH - 4)
                if ref_lines:
                    lines.append(f"  {index}. {ref_lines[0]}")
                    for continuation in ref_lines[1:]:
                        lines.append(f"      {continuation}")
            lines.append("")

        text = "\n".join(lines).rstrip() + "\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


def _text_table(rows) -> List[str]:
    if not rows:
        return []
    column_count = max(len(row) for row in rows)
    normalized = [
        [(row[c] if c < len(row) else "") for c in range(column_count)] for row in rows
    ]
    widths = [
        max(len(normalized[r][c]) for r in range(len(normalized)))
        for c in range(column_count)
    ]
    lines: List[str] = []
    for row_index, row in enumerate(normalized):
        cells = [cell.ljust(widths[c]) for c, cell in enumerate(row)]
        lines.append(" | ".join(cells).rstrip())
        if row_index == 0:
            lines.append("-+-".join("-" * w for w in widths))
    return lines
