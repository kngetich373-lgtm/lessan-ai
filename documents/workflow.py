"""Workflow Engine integration for the Professional Document Intelligence
System.

Registers a :class:`DocumentWorkflow` (resolve → draft → format → export)
with the shared :class:`WorkflowEngine`. The workflow carries the full
request as step parameters; the host application maps the step ``action``
names to :class:`DocumentGenerator` calls (see ``documents/action.py`` for
the reference mapping).
"""

from __future__ import annotations

from typing import Optional

from core.logging import get_logger
from core.workflow.models import Workflow, WorkflowStep

from documents.models import DocumentRequest

logger = get_logger("documents.workflow")

WORKFLOW_NAME = "document_generation"

#: Action names used by the workflow steps (host-dispatched).
ACTION_RESOLVE = "documents.resolve"
ACTION_DRAFT = "documents.draft"
ACTION_FORMAT = "documents.format"
ACTION_EXPORT = "documents.export"


def build_document_workflow(request: Optional[DocumentRequest] = None) -> Workflow:
    """Build the document-generation workflow for a request."""
    req = request or DocumentRequest()
    steps = [
        WorkflowStep(
            name="resolve",
            action=ACTION_RESOLVE,
            params={"request": req.to_dict()},
            depends_on=[],
        ),
        WorkflowStep(
            name="draft",
            action=ACTION_DRAFT,
            params={"request": req.to_dict()},
            depends_on=["resolve"],
        ),
        WorkflowStep(
            name="format",
            action=ACTION_FORMAT,
            params={"request": req.to_dict()},
            depends_on=["draft"],
        ),
        WorkflowStep(
            name="export",
            action=ACTION_EXPORT,
            params={"request": req.to_dict()},
            depends_on=["format"],
        ),
    ]
    workflow = Workflow(name=WORKFLOW_NAME, steps=steps)
    workflow.context.metadata["description"] = (
        "Generate a professional document: resolve kind and formats, draft "
        "content, apply publishing formatting, then export."
    )
    return workflow


class DocumentWorkflow(Workflow):
    """Workflow class compatible with the WorkflowEngine registry.

    The engine instantiates this class with no arguments and stamps
    ``workflow.name``. Concrete request parameters are supplied by the host
    when running (see :func:`build_document_workflow`).
    """

    def __init__(self) -> None:
        super().__init__(name=WORKFLOW_NAME, steps=[])
        self.steps = build_document_workflow().steps


def register_document_workflow(engine=None):
    """Register the document workflow with a WorkflowEngine.

    Args:
        engine: A :class:`core.workflow.engine.WorkflowEngine`. When None, the
            engine is resolved from the DI container (creating one if needed).
    """
    from core.di.container import container
    from core.workflow.engine import WorkflowEngine

    if engine is None:
        try:
            engine = container.try_resolve(WorkflowEngine)
        except Exception:  # noqa: BLE001
            engine = None
    if engine is None:
        engine = WorkflowEngine()
        try:
            container.register_instance(WorkflowEngine, engine)
        except Exception:  # noqa: BLE001
            pass

    try:
        engine.registry.register(WORKFLOW_NAME, DocumentWorkflow)
    except Exception as exc:  # noqa: BLE001 - already registered or host-specific
        logger.warning(f"Could not register document workflow: {exc}")
    return engine
