"""Format builders for the Professional Document Intelligence System.

Each builder renders the same format-agnostic
:class:`~documents.formatter.FormattedProject` in one output format. The
``builtin_builders`` list is consumed by :class:`ExportManager`; individual
builders can be swapped or extended by registering custom subclasses.
"""

from __future__ import annotations

from documents.builders.base import FormatBuilder
from documents.builders.docx_builder import DocxBuilder
from documents.builders.html_builder import HTMLBuilder
from documents.builders.markdown_builder import MarkdownBuilder
from documents.builders.pdf_builder import PdfBuilder
from documents.builders.rtf_builder import RTFBuilder
from documents.builders.text_builder import TextBuilder

builtin_builders = [
    DocxBuilder,
    PdfBuilder,
    MarkdownBuilder,
    TextBuilder,
    HTMLBuilder,
    RTFBuilder,
]

__all__ = [
    "FormatBuilder",
    "DocxBuilder",
    "PdfBuilder",
    "MarkdownBuilder",
    "TextBuilder",
    "HTMLBuilder",
    "RTFBuilder",
    "builtin_builders",
]
