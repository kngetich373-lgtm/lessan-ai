"""Dependency Injection registration for the Professional Document
Intelligence System.

Call :func:`register_document_system` once at application startup (or rely on
the idempotent auto-registration at import time). Subsystems resolve
:class:`DocumentGenerator` through the DI container without direct imports.
Optional cross-subsystem services (Model Router, Memory) are resolved lazily
and degraded gracefully when absent, so the document system works standalone.
"""

from __future__ import annotations

from typing import Optional

from core.logging import get_logger

logger = get_logger("documents.di")


def register_document_system(container=None, config=None, event_bus=None):
    """Register all document-system components in the DI container.

    Idempotent — safe to call multiple times. Registers:
      - :class:`~documents.style_manager.StyleManager`
      - :class:`~documents.types.DocumentTypeRegistry`
      - :class:`~documents.template_manager.DocumentTemplateManager`
      - :class:`~documents.resolver.DocumentResolver`
      - :class:`~documents.exporters.ExportManager`
      - :class:`~documents.content.ContentGenerator`
      - :class:`~documents.formatter.DocumentFormatter`
      - :class:`~documents.generator.DocumentGenerator`

    Args:
        container: The DI container (``core.di.Container``).
        config: Optional configuration object (currently unused).
        event_bus: Optional event bus instance.
    """
    from core.di.container import container as global_container
    from documents.content import ContentGenerator
    from documents.exporters import ExportManager
    from documents.formatter import DocumentFormatter
    from documents.generator import DocumentGenerator
    from documents.resolver import DocumentResolver
    from documents.style_manager import StyleManager
    from documents.template_manager import DocumentTemplateManager
    from documents.types import DocumentTypeRegistry

    container = container or global_container
    if container.has(DocumentGenerator):
        return container

    style_manager = container.try_resolve(StyleManager) or StyleManager()
    registry = container.try_resolve(DocumentTypeRegistry) or DocumentTypeRegistry()
    templates = container.try_resolve(DocumentTemplateManager) or DocumentTemplateManager()

    resolver = DocumentResolver(registry)
    exporters = ExportManager()
    formatter = DocumentFormatter(style_manager)

    router = _resolve_model_router(container)
    memory_store = _resolve_memory_store(container)
    content = ContentGenerator(model_router=router, memory_store=memory_store)

    generator = DocumentGenerator(
        registry=registry,
        templates=templates,
        resolver=resolver,
        content=content,
        formatter=formatter,
        exporters=exporters,
        memory_store=memory_store,
        event_bus=event_bus,
    )

    container.register_instance(StyleManager, style_manager)
    container.register_instance(DocumentTypeRegistry, registry)
    container.register_instance(DocumentTemplateManager, templates)
    container.register_instance(DocumentResolver, resolver)
    container.register_instance(ExportManager, exporters)
    container.register_instance(ContentGenerator, content)
    container.register_instance(DocumentFormatter, formatter)
    container.register_instance(DocumentGenerator, generator)

    logger.info("Registered Professional Document Intelligence System in DI container")
    return container


def unregister_document_system(container) -> None:
    """Remove the document-system registrations (mainly for tests)."""
    from documents.content import ContentGenerator
    from documents.exporters import ExportManager
    from documents.formatter import DocumentFormatter
    from documents.generator import DocumentGenerator
    from documents.resolver import DocumentResolver
    from documents.style_manager import StyleManager
    from documents.template_manager import DocumentTemplateManager
    from documents.types import DocumentTypeRegistry

    for service in (
        StyleManager,
        DocumentTypeRegistry,
        DocumentTemplateManager,
        DocumentResolver,
        ExportManager,
        ContentGenerator,
        DocumentFormatter,
        DocumentGenerator,
    ):
        try:
            container.remove(service)
        except Exception:  # noqa: BLE001
            pass


def _resolve_model_router(container):
    """Resolve the Model Router through either the orchestrator ABC or the
    concrete router class; returns None when unavailable."""
    try:
        from core.orchestrator.interfaces import ModelRouter as IModelRouter

        router = container.try_resolve(IModelRouter)
        if router is not None:
            return router
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Orchestrator ModelRouter not available: {exc}")
    try:
        from core.model_router.router import ModelRouter

        return container.try_resolve(ModelRouter)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Concrete ModelRouter not available: {exc}")
    return None


def _resolve_memory_store(container):
    """Resolve the orchestrator MemoryStore adapter; None when unavailable."""
    try:
        from core.orchestrator.interfaces import MemoryStore

        return container.try_resolve(MemoryStore)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"MemoryStore not available: {exc}")
        return None


def _auto_register_document_system() -> None:
    try:
        from core.di.container import container as global_container

        register_document_system(global_container)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Auto-registration skipped: {exc}")


_auto_register_document_system()
