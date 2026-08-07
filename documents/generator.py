"""The :class:`DocumentGenerator` — the public facade of the Professional
Document Intelligence System.

Pipeline: resolve kind → resolve formats → select template → gather memory →
generate content (AI w/ skeleton fallback) → format (numbering/TOC/captions)
→ export to every requested format → record to memory → return a
:class:`DocumentResult`. Every stage emits an event.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.logging import get_logger

from documents.content import ContentGenerator
from documents.events import (
    EV_DOCUMENT_CONTENT_READY,
    EV_DOCUMENT_EXPORTED,
    EV_DOCUMENT_FAILED,
    EV_DOCUMENT_FORMATTED,
    EV_DOCUMENT_GENERATED,
    EV_DOCUMENT_KIND_RESOLVED,
    EV_DOCUMENT_STARTED,
    EV_DOCUMENT_TEMPLATE_SELECTED,
    emit_document_event,
)
from documents.exporters import ExportManager
from documents.formatter import DocumentFormatter, FormattedProject
from documents.models import DocumentProject, DocumentRequest, DocumentResult, OutputFormat
from documents.resolver import DocumentResolver
from documents.template_manager import DocumentTemplateManager
from documents.types import DocumentType, DocumentTypeRegistry

logger = get_logger("documents.generator")


class DocumentGenerator:
    """Coordinates the full document generation pipeline."""

    def __init__(
        self,
        registry: Optional[DocumentTypeRegistry] = None,
        templates: Optional[DocumentTemplateManager] = None,
        resolver: Optional[DocumentResolver] = None,
        content: Optional[ContentGenerator] = None,
        formatter: Optional[DocumentFormatter] = None,
        exporters: Optional[ExportManager] = None,
        memory_store: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry or DocumentTypeRegistry()
        self._templates = templates or DocumentTemplateManager()
        self._resolver = resolver or DocumentResolver(self._registry)
        self._content = content or ContentGenerator()
        self._formatter = formatter or DocumentFormatter()
        self._exporters = exporters or ExportManager()
        self._memory = memory_store
        self._bus = event_bus

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def list_document_types(self) -> str:
        return self._registry.summary()

    def list_templates(self) -> str:
        return self._templates.summary()

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    def generate(self, request: DocumentRequest) -> DocumentResult:
        self._emit(EV_DOCUMENT_STARTED, {"topic": request.topic})
        try:
            doc_type = self._resolver.resolve_kind(
                text=request.text, explicit=request.document_type
            )
            self._emit(EV_DOCUMENT_KIND_RESOLVED, {"kind": doc_type.type_id})

            formats = self._resolver.resolve_format(
                text=request.text, explicit=request.formats
            )
            template = self._templates.select(
                explicit=request.template,
                kind_default=doc_type.default_template,
                text=request.text,
            )
            self._emit(
                EV_DOCUMENT_TEMPLATE_SELECTED,
                {"template": template.template_id, "kind": doc_type.type_id},
            )

            memory = self._load_memory()
            project = self._content.generate(request, doc_type, memory)
            project.kind = doc_type.type_id
            project.template = template.template_id
            self._emit(EV_DOCUMENT_CONTENT_READY, {"title": project.title})

            formatted = self._formatter.format(
                project, template, self._style_overrides(request, doc_type)
            )
            self._emit(EV_DOCUMENT_FORMATTED, {"title": formatted.title})

            paths = self._export(formatted, request)
            self._emit(EV_DOCUMENT_EXPORTED, {"paths": list(paths.values())})

            result = DocumentResult(
                request=request,
                kind=doc_type.type_id,
                template=template.template_id,
                title=formatted.title,
                paths=paths,
                generated_from=str(project.metadata.get("generated_from", "template")),
                metadata=dict(project.metadata),
            )
            self._remember(request, result)
            self._emit(
                EV_DOCUMENT_GENERATED,
                {
                    "kind": result.kind,
                    "template": result.template,
                    "paths": list(paths.values()),
                    "generated_from": result.generated_from,
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001 - structured failure result
            logger.exception(f"Document generation failed: {exc}")
            self._emit(EV_DOCUMENT_FAILED, {"error": str(exc)})
            raise

    def generate_from_project(
        self,
        request: DocumentRequest,
        project: DocumentProject,
    ) -> DocumentResult:
        """Generate outputs from an already-built project (no AI call)."""
        doc_type = self._resolver.resolve_kind(
            text=request.text, explicit=request.document_type
        )
        formats = self._resolver.resolve_format(text=request.text, explicit=request.formats)
        template = self._templates.select(
            explicit=request.template,
            kind_default=doc_type.default_template,
            text=request.text,
        )
        project.kind = project.kind or doc_type.type_id
        project.template = template.template_id
        formatted = self._formatter.format(
            project, template, self._style_overrides(request, doc_type)
        )
        paths = self._export(formatted, request)
        result = DocumentResult(
            request=request,
            kind=project.kind,
            template=template.template_id,
            title=formatted.title,
            paths=paths,
            generated_from=str(project.metadata.get("generated_from", "template")),
            metadata=dict(project.metadata),
        )
        self._remember(request, result)
        return result

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _style_overrides(
        self, request: DocumentRequest, doc_type: DocumentType
    ) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {
            "toc_enabled": bool(doc_type.toc),
            "title_page": bool(doc_type.title_page),
        }
        if request.font_family:
            overrides["font_family"] = request.font_family
        if request.line_spacing:
            overrides["line_spacing"] = request.line_spacing
        if request.toc is not None:
            overrides["toc_enabled"] = request.toc
        if request.title_page is not None:
            overrides["title_page"] = request.title_page
        return overrides

    def _load_memory(self) -> Optional[Dict[str, Any]]:
        if self._memory is None:
            return None
        try:
            return self._memory.load()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not load memory for document generation: {exc}")
            return None

    def _export(
        self,
        formatted: FormattedProject,
        request: DocumentRequest,
    ) -> Dict[OutputFormat, str]:
        paths: Dict[OutputFormat, str] = {}
        for fmt in request.formats:
            if not self._exporters.supports(fmt):
                logger.warning(f"Format '{fmt.value}' has no builder; skipping")
                continue
            try:
                paths[fmt] = self._exporters.export(
                    formatted, fmt, output_name=request.output_name
                )
            except Exception as exc:  # noqa: BLE001 - one format must not block the rest
                logger.error(f"Export to {fmt.value} failed: {exc}")
        if not paths:
            raise RuntimeError(
                "No export format could be written. Ensure at least one builder "
                f"is available for: {[f.value for f in request.formats]}"
            )
        return paths

    def _remember(self, request: DocumentRequest, result: DocumentResult) -> None:
        if self._memory is None:
            return
        try:
            record = {
                "type": result.kind,
                "title": result.title,
                "topic": request.topic,
                "template": result.template,
                "paths": {fmt.value: p for fmt, p in result.paths.items()},
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._memory.save({"documents.last": record})
            try:
                existing = self._memory.load().get("documents.log") or []
                if isinstance(existing, list):
                    existing = existing[-19:]
                    existing.append(record)
                    self._memory.save({"documents.log": existing})
                else:
                    self._memory.save({"documents.log": [record]})
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Could not append to documents.log: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not record document to memory: {exc}")

    def _emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        emit_document_event(event, payload, bus=self._bus)

