"""Markdown builder — clean, portable Markdown export."""

from __future__ import annotations

import re
from typing import List

from documents.builders.base import FormatBuilder
from documents.models import OutputFormat


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", text.strip().lower()).strip("-")
    return slug or "section"


def _md_table(rows, header_row: bool) -> List[str]:
    if not rows:
        return []
    column_count = max(len(row) for row in rows)
    normalized = [
        [(row[c] if c < len(row) else "") for c in range(column_count)] for row in rows
    ]
    lines = ["| " + " | ".join(normalized[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(column_count)) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return lines


class MarkdownBuilder(FormatBuilder):
    """Exports the document as a GitHub-flavoured Markdown file."""

    output_format = OutputFormat.MD

    def build(self, formatted, path: str) -> str:
        style = formatted.style
        lines: List[str] = [f"# {formatted.title}"]

        if formatted.subtitle:
            lines.append(f"*{formatted.subtitle}*")
        lines.append("")
        lines.append(f"**{formatted.author}** — {formatted.date}")
        lines.append("")
        lines.append("---")
        lines.append("")

        if formatted.toc:
            lines.append("## Table of Contents")
            for entry in formatted.toc_entries:
                indent = "  " * (entry.level - 1)
                anchor = _slugify(f"{entry.number} {entry.heading}")
                lines.append(f"{indent}- [{entry.label}](#{anchor})")
            lines.append("")

        for section in formatted.project.sections:
            number = section.meta.get("number", "")
            heading = f"{number}  {section.heading}".strip()
            lines.append(f"{'#' * min(6, section.level + 1)} {heading}")
            lines.append("")

            for paragraph in section.paragraphs:
                lines.append(paragraph.text)
                lines.append("")

            for item in section.bullets:
                lines.append(f"- {item}")
            if section.bullets:
                lines.append("")

            for index, item in enumerate(section.numbered, start=1):
                lines.append(f"{index}. {item}")
            if section.numbered:
                lines.append("")

            for table in section.tables:
                if table.caption:
                    lines.append(f"*{table.caption}*")
                lines.extend(_md_table(table.rows, table.header_row))
                lines.append("")

            for figure in section.figures:
                if figure.path:
                    lines.append(f"![{figure.caption}]({figure.path})")
                lines.append(f"*{figure.caption}*")
                lines.append("")

            for code_block in section.code_blocks:
                lines.append(f"```{code_block.language}")
                lines.append(code_block.text.rstrip("\n"))
                lines.append("```")
                lines.append("")

            for reference in section.references:
                lines.append(f"- {reference}")
            if section.references:
                lines.append("")

            if section.page_break_after:
                lines.append("<div style='page-break-after: always;'></div>")
                lines.append("")

        text = "\n".join(lines).rstrip() + "\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path
