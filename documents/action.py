"""Tool action for the Professional Document Intelligence System.

Exposes :func:`generate_document` to the main dispatcher. Resolves the
:class:`DocumentGenerator` through the DI container (auto-registering the
subsystem on first use), generates the document, auto-opens the primary
export, and returns a human-readable result summary.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.logging import get_logger

from documents.exporters import open_file
from documents.generator import DocumentGenerator
from documents.models import DocumentRequest

logger = get_logger("documents.action")

TOOL_NAME = "generate_document"

TOOL_DESCRIPTION = (
    "Generate a professional document (proposal, CV, report, invoice, "
    "manual, meeting minutes, etc.) in DOCX, PDF, Markdown, HTML, RTF or "
    "plain text. If you only know the type or format from the user's words, "
    "pass them in 'document_type' or 'formats'."
)

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": TOOL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "document_type": {
                "type": "string",
                "description": (
                    "Type id or alias: research_proposal, thesis, resume/cv, "
                    "cover_letter, business_plan, technical_documentation, "
                    "software_requirements/srs, software_design, project_report, "
                    "meeting_minutes, user_manual, api_documentation, "
                    "presentation, letter, invoice, quotation, report."
                ),
            },
            "topic": {"type": "string", "description": "Subject/title of the document."},
            "content": {
                "type": "string",
                "description": "User-supplied raw content to incorporate and rewrite.",
            },
            "instructions": {
                "type": "string",
                "description": "Extra instructions for tone, length or details.",
            },
            "formats": {
                "type": "string",
                "description": "Comma-separated export formats: docx, pdf, md, txt, html, rtf. Defaults to docx.",
            },
            "template": {
                "type": "string",
                "description": "Template id: academic, business, software_engineering, legal, research, corporate, generic.",
            },
            "output_name": {
                "type": "string",
                "description": "Base filename (without extension) for the generated files.",
            },
            "author": {"type": "string", "description": "Author name for the title page."},
        },
        "required": [],
    },
}


def generate_document(
    parameters: Optional[Dict[str, Any]] = None,
    player: Any = None,
    speak: Any = None,
) -> str:
    """Tool entry point: generate a professional document from parameters."""
    parameters = parameters or {}
    generator = _get_generator()
    request = DocumentRequest.from_dict(parameters)

    logger.info(
        f"Generating document: type={request.document_type or 'auto'} "
        f"topic={request.topic!r} formats={[f.value for f in request.formats]}"
    )
    result = generator.generate(request)

    primary = result.primary_path()
    if primary:
        open_file(primary)

    lines = [f"Document generated: {result.title}"]
    lines.append(
        f"  Type: {result.kind} · Template: {result.template} · "
        f"Content: {result.generated_from}"
    )
    for fmt, path in result.paths.items():
        lines.append(f"  {fmt.value.upper()}: {path}")

    summary = "\n".join(lines)
    logger.info(summary)
    return summary


def list_document_types(
    parameters: Optional[Dict[str, Any]] = None,
    player: Any = None,
    speak: Any = None,
) -> str:
    """Tool entry point: list supported document types and templates."""
    generator = _get_generator()
    types = generator.list_document_types()
    templates = generator.list_templates()
    return (
        "Supported document types:\n"
        f"{types}\n\n"
        "Available templates:\n"
        f"{templates}"
    )


def _get_generator() -> DocumentGenerator:
    try:
        from core.di.container import container

        from documents.di import register_document_system

        register_document_system(container)
        return container.resolve(DocumentGenerator)
    except Exception as exc:  # noqa: BLE001 - standalone fallback
        logger.warning(f"Container unavailable; using standalone generator: {exc}")
        return DocumentGenerator()
