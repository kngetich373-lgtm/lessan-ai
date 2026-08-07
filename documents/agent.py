"""DocumentAgent — exposes the Professional Document Intelligence System as a
Lessan AI agent with three capabilities:

* ``generate_document`` — generate a document from a request dict
* ``list_document_types`` — show the supported document taxonomy
* ``list_templates`` — show the available reusable templates
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.framework.agent_registry import agent_registry
from agents.framework.base_agent import BaseAgent, AgentTask
from core.logging import get_logger

from documents.generator import DocumentGenerator
from documents.models import DocumentRequest

logger = get_logger("documents.agent")


@agent_registry.register
class DocumentAgent(BaseAgent):
    """Generates professional documents in multiple export formats."""

    name = "document_generator"
    display_name = "Document Generator"
    description = (
        "Generates professional documents — proposals, CVs, reports, "
        "invoices, manuals, meeting minutes and more — in DOCX, PDF, "
        "Markdown, HTML, RTF and plain text."
    )
    icon = "📄"
    color = "#0ea5e9"

    def __init__(self, generator: Optional[DocumentGenerator] = None) -> None:
        super().__init__()
        self._generator = generator

    def on_initialize(self, config: Dict[str, Any]) -> None:
        if self._generator is None:
            self._generator = _default_generator()
        self.register_capability(
            "generate_document",
            "Generate a professional document and export it to the requested formats.",
            self._cap_generate,
            {
                "document_type": {"type": "string", "description": "e.g. research_proposal, resume, invoice"},
                "topic": {"type": "string"},
                "content": {"type": "string"},
                "instructions": {"type": "string"},
                "formats": {"type": "string", "description": "comma-separated: docx, pdf, md, txt, html, rtf"},
                "template": {"type": "string"},
                "output_name": {"type": "string"},
            },
        )
        self.register_capability(
            "list_document_types",
            "List the supported professional document types.",
            self._cap_list_types,
        )
        self.register_capability(
            "list_templates",
            "List the available reusable document templates.",
            self._cap_list_templates,
        )

    # ------------------------------------------------------------------ #
    # Capability handlers
    # ------------------------------------------------------------------ #
    def _cap_generate(self, **kwargs: Any) -> Dict[str, Any]:
        request = DocumentRequest.from_dict(kwargs)
        generator = self._generator or _default_generator()
        result = generator.generate(request)
        return {
            "title": result.title,
            "type": result.kind,
            "template": result.template,
            "generated_from": result.generated_from,
            "paths": {fmt.value: path for fmt, path in result.paths.items()},
            "summary": result.summary(),
        }

    def _cap_list_types(self, **kwargs: Any) -> str:
        generator = self._generator or _default_generator()
        return generator.list_document_types()

    def _cap_list_templates(self, **kwargs: Any) -> str:
        generator = self._generator or _default_generator()
        return generator.list_templates()

    def on_run(self, task: AgentTask) -> Any:
        desc = (task.description or "").strip().lower()
        if desc.startswith(("generate", "make", "create", "write", "draft")):
            return "Use the 'generate_document' capability with a request dict."
        if "type" in desc or "template" in desc:
            return "Use 'list_document_types' or 'list_templates'."
        return self.description


def _default_generator() -> DocumentGenerator:
    """Resolve the generator from the DI container, or build a standalone one."""
    try:
        from core.di.container import container

        from documents.di import register_document_system

        register_document_system(container)
        return container.resolve(DocumentGenerator)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Falling back to standalone DocumentGenerator: {exc}")
        return DocumentGenerator()


def register_document_agent(manager=None):
    """Register and spawn the DocumentAgent.

    Args:
        manager: The agent manager. When None, ``agents.framework.agent_manager``
            is used. The agent type is registered via the ``@agent_registry.register``
            decorator, so spawning only needs the type name.
    """
    try:
        from agents.framework.agent_manager import agent_manager

        manager = manager or agent_manager
        return manager.spawn(DocumentAgent.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not spawn DocumentAgent: {exc}")
        try:
            return agent_registry.get_or_create(DocumentAgent.name)
        except Exception as inner:  # noqa: BLE001
            logger.warning(f"Could not create DocumentAgent: {inner}")
            return DocumentAgent()

