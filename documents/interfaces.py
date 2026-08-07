"""Interfaces for the Professional Document Intelligence System.

Concrete implementations are wired in :mod:`documents.di`. Cross-subsystem
dependencies (Model Router, Memory) are injected through the System
Orchestrator ABCs in :mod:`core.orchestrator.interfaces` so this package
never imports concrete provider modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from documents.models import DocumentProject, DocumentRequest


class IContentGenerator(ABC):
    """Produces a format-agnostic :class:`DocumentProject` for a request."""

    @abstractmethod
    def generate(
        self,
        request: DocumentRequest,
        doc_type: Any,
        memory: Optional[Dict[str, Any]] = None,
    ) -> DocumentProject:
        """Generate content for ``doc_type``; must never raise on fallback."""

    @abstractmethod
    def build_skeleton(self, request: DocumentRequest, doc_type: Any) -> DocumentProject:
        """Deterministic, offline-safe skeleton using the doc-type schema."""


class IDocumentExporter(ABC):
    """Renders a formatted document to a single output path."""

    @abstractmethod
    def export(
        self,
        formatted: Any,
        path: str,
        style: Any,
    ) -> str:
        """Render ``formatted`` to ``path`` and return the path."""
