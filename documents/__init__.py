"""Professional Document Intelligence System for Lessan AI.

Generates professional documents (proposals, CVs, reports, invoices, manuals,
meeting minutes, …) with publishing-standard formatting and multiple export
formats (DOCX, PDF, Markdown, HTML, RTF, plain text).

Quick start (standalone):

    >>> from documents import DocumentGenerator, DocumentRequest
    >>> request = DocumentRequest(document_type="research_proposal", topic="Edge AI")
    >>> result = DocumentGenerator().generate(request)
    >>> result.summary()
"""

from documents.agent import DocumentAgent
from documents.content import ContentGenerator
from documents.di import register_document_system, unregister_document_system
from documents.events import (
    EV_DOCUMENT_CONTENT_READY,
    EV_DOCUMENT_EXPORTED,
    EV_DOCUMENT_FAILED,
    EV_DOCUMENT_FORMATTED,
    EV_DOCUMENT_GENERATED,
    EV_DOCUMENT_KIND_RESOLVED,
    EV_DOCUMENT_STARTED,
    EV_DOCUMENT_TEMPLATE_SELECTED,
)
from documents.exporters import ExportManager
from documents.formatter import DocumentFormatter, FormattedProject
from documents.generator import DocumentGenerator
from documents.models import (
    DocumentProject,
    DocumentRequest,
    DocumentResult,
    DocumentSection,
    OutputFormat,
)
from documents.resolver import DocumentResolver
from documents.style_manager import StyleManager, StyleSpec
from documents.template_manager import DocumentTemplate, DocumentTemplateManager
from documents.types import DocumentType, DocumentTypeRegistry
from documents.workflow import build_document_workflow, register_document_workflow

__version__ = "1.0.0"

__all__ = [
    "DocumentGenerator",
    "DocumentRequest",
    "DocumentResult",
    "DocumentProject",
    "DocumentSection",
    "OutputFormat",
    "DocumentType",
    "DocumentTypeRegistry",
    "DocumentTemplate",
    "DocumentTemplateManager",
    "StyleManager",
    "StyleSpec",
    "DocumentFormatter",
    "FormattedProject",
    "DocumentResolver",
    "ContentGenerator",
    "DocumentAgent",
    "ExportManager",
    "build_document_workflow",
    "register_document_workflow",
    "register_document_system",
    "unregister_document_system",
    "EV_DOCUMENT_STARTED",
    "EV_DOCUMENT_KIND_RESOLVED",
    "EV_DOCUMENT_TEMPLATE_SELECTED",
    "EV_DOCUMENT_CONTENT_READY",
    "EV_DOCUMENT_FORMATTED",
    "EV_DOCUMENT_EXPORTED",
    "EV_DOCUMENT_GENERATED",
    "EV_DOCUMENT_FAILED",
]
