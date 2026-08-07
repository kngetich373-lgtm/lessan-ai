"""HTML builder — print-ready HTML with CSS page chrome."""

from __future__ import annotations

import html as html_module
import re
from typing import List

from documents.builders.base import FormatBuilder
from documents.models import OutputFormat


class HTMLBuilder(FormatBuilder):
    """Exports the document as a self-contained HTML file."""

    output_format = OutputFormat.HTML

    def build(self, formatted, path: str) -> str:
        style = formatted.style
        css = _render_css(formatted, style)
        body = self._render_body(formatted, style)
        page = (
            "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
            "<meta charset='utf-8'>\n"
            f"<title>{html_module.escape(formatted.title)}</title>\n"
            f"<style>{css}</style>\n"
            "</head>\n<body>\n"
            f"{body}\n</body>\n</html>\n"
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(page)
        return path

    def _render_body(self, formatted, style) -> str:
        parts: List[str] = []
        if style.header_enabled:
            header_text = style.header_text or formatted.title
            parts.append(f"<div class='rh'>{html_module.escape(header_text)}</div>")
        if style.footer_text or style.page_numbers:
            parts.append(
                "<div class='rf'>"
                f"<span>{html_module.escape(style.footer_text)}</span>"
                + (" <span class='pn'></span>" if style.page_numbers else "")
                + "</div>"
            )
        if formatted.title_page:
            parts.append("<div class='tp'>")
            parts.append(f"<h1 class='dt'>{html_module.escape(formatted.title)}</h1>")
            if formatted.subtitle:
                parts.append(f"<p class='ds'>{html_module.escape(formatted.subtitle)}</p>")
            parts.append(f"<p class='da'>{html_module.escape(formatted.author)}</p>")
            parts.append(f"<p class='dd'>{html_module.escape(formatted.date)}</p>")
            parts.append("</div>")
        if formatted.toc:
            parts.append("<div class='toc'><h2>Table of Contents</h2><ul>")
            for entry in formatted.toc_entries:
                indent = f" style='margin-left:{(entry.level - 1) * 14}pt'"
                anchor = _anchor(f"{entry.number} {entry.heading}")
                parts.append(f"<li{indent}><a href='#{anchor}'>{html_module.escape(entry.label)}</a></li>")
            parts.append("</ul></div><div class='pb'></div>")
        for section in formatted.project.sections:
            parts.append(self._render_section(section, style))
        if formatted.project.references and not any(
            s.references for s in formatted.project.sections
        ):
            parts.append("<div class='refs'><h2>References</h2><ol>")
            for ref in formatted.project.references:
                parts.append(f"<li>{html_module.escape(ref)}</li>")
            parts.append("</ol></div>")
        return "\n".join(parts)

    def _render_section(self, section, style) -> str:
        number = section.meta.get("number", "")
        heading = f"{number}  {section.heading}".strip()
        level = min(6, section.level + 1)
        parts = [f"<h{level} id='{_anchor(heading)}'>{html_module.escape(heading)}</h{level}>"]
        for p in section.paragraphs:
            cls = " class='q'" if p.style == "quote" else ""
            parts.append(f"<p{cls}>{html_module.escape(p.text)}</p>")
        if section.bullets:
            parts.append("<ul>")
            parts.extend(f"<li>{html_module.escape(item)}</li>" for item in section.bullets)
            parts.append("</ul>")
        if section.numbered:
            parts.append("<ol>")
            parts.extend(f"<li>{html_module.escape(item)}</li>" for item in section.numbered)
            parts.append("</ol>")
        for table in section.tables:
            if table.caption:
                parts.append(f"<p class='cap'>{html_module.escape(table.caption)}</p>")
            parts.append("<table>")
            for ri, row in enumerate(table.rows):
                tag = "th" if (ri == 0 and table.header_row) else "td"
                parts.append("<tr>" + "".join(f"<{tag}>{html_module.escape(c)}</{tag}>" for c in row) + "</tr>")
            parts.append("</table>")
        for fig in section.figures:
            if fig.path:
                parts.append(f"<figure><img src='{html_module.escape(str(fig.path))}' alt=''>")
                parts.append(f"<figcaption>{html_module.escape(fig.caption)}</figcaption></figure>")
            else:
                parts.append(f"<p class='cap'>{html_module.escape(fig.caption)}</p>")
        for cb in section.code_blocks:
            parts.append(f"<pre><code>{html_module.escape(cb.text)}</code></pre>")
        for ref in section.references:
            parts.append(f"<p class='ref'>{html_module.escape(ref)}</p>")
        if section.page_break_after:
            parts.append("<div class='pb'></div>")
        return "\n".join(parts)


def _anchor(heading: str) -> str:
    slug = re.sub(r"[^\w]+", "-", heading.strip().lower()).strip("-")
    return slug or "section"


def _render_css(formatted, style) -> str:
    h1_size = style.heading_sizes[0] if style.heading_sizes else 16
    h2_size = style.heading_sizes[1] if len(style.heading_sizes) > 1 else 14
    h3_size = style.heading_sizes[2] if len(style.heading_sizes) > 2 else 12
    h4_size = style.heading_sizes[3] if len(style.heading_sizes) > 3 else 12
    return f"""
:root {{ --hc: {style.heading_color}; --font: {style.font_family}, serif; --mono: {style.mono_family}, monospace; }}
@page {{ size: letter; margin: {style.margin_inches}in; }}
body {{ font-family: var(--font); font-size: {style.base_size}pt; line-height: {style.line_spacing}; color: #1a1a1a; max-width: 6.5in; margin: 0 auto; }}
.rh {{ position: fixed; top: 0; left: 0; right: 0; text-align: right; font-size: 9pt; color: #666; border-bottom: 0.5pt solid #bbb; padding-bottom: 2pt; }}
.rf {{ position: fixed; bottom: 0; left: 0; right: 0; text-align: center; font-size: 9pt; color: #666; }}
.pn::after {{ content: counter(page); }}
.tp {{ height: 8.5in; display: flex; flex-direction: column; justify-content: center; text-align: center; page-break-after: always; }}
.dt {{ font-size: 26pt; margin: 0 0 12pt; color: var(--hc); }}
.ds {{ font-size: 15pt; font-style: italic; color: #444; margin: 0 0 48pt; }}
.da, .dd {{ font-size: 12pt; margin: 2pt 0; }}
.toc ul {{ list-style: none; padding-left: 0; }}
.toc li {{ margin: 3pt 0; }}
.toc a {{ text-decoration: none; color: inherit; }}
h2 {{ font-size: {h1_size}pt; color: var(--hc); page-break-after: avoid; }}
h3 {{ font-size: {h2_size}pt; color: var(--hc); page-break-after: avoid; }}
h4, h5, h6 {{ font-size: {h3_size}pt; color: var(--hc); page-break-after: avoid; }}
p {{ margin: 0 0 {style.space_after_pt}pt; text-align: justify; }}
p.q {{ margin-left: 18pt; font-style: italic; }}
ul, ol {{ margin: 0 0 {style.space_after_pt}pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 0 0 {style.space_after_pt}pt; }}
th, td {{ border: 0.5pt solid #999; padding: 4pt 8pt; text-align: left; vertical-align: top; }}
th {{ background: #e8edf5; }}
p.cap, figcaption {{ font-style: italic; text-align: center; font-size: {style.base_size - 1}pt; margin: 4pt 0 8pt; }}
figure {{ margin: 0 0 {style.space_after_pt}pt; text-align: center; }}
figure img {{ max-width: 100%; }}
pre {{ font-family: var(--mono); font-size: {style.base_size - 1}pt; background: #f5f5f5; border: 0.5pt solid #ddd; padding: 8pt; margin: 0 0 {style.space_after_pt}pt; white-space: pre-wrap; line-height: 1.2; }}
p.ref {{ margin-left: 24pt; text-indent: -12pt; font-size: {style.base_size - 1}pt; }}
.pb {{ page-break-after: always; }}
"""

