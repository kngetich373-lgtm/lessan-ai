"""Reusable document templates.

Templates are presentation profiles (fonts, spacing, colours, TOC/title-page
behaviour) bundled with domain keywords used for automatic selection. They
never carry content — only :class:`StyleSpec` tweaks layered on the publishing
defaults.

Selection order (see :meth:`DocumentTemplateManager.select`):
explicit template id → per-kind default → keyword scoring → generic template.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from documents.style_manager import StyleSpec


@dataclass
class DocumentTemplate:
    """A reusable presentation profile."""

    template_id: str
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    default_kinds: List[str] = field(default_factory=list)
    style: Optional[StyleSpec] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "keywords": list(self.keywords),
            "default_kinds": list(self.default_kinds),
            "style": self.style.to_dict() if self.style else None,
        }


_BUILTIN_TEMPLATES: List[DocumentTemplate] = [
    DocumentTemplate(
        template_id="academic",
        name="Academic",
        description="For theses, dissertations, research proposals and journal-style papers.",
        keywords=[
            "academic", "university", "thesis", "dissertation", "research",
            "journal", "peer", "seminar", "coursework", "faculty", "study",
            "scholar", "citation",
        ],
        default_kinds=["thesis", "research_proposal"],
        style=StyleSpec(
            heading_color="#1F3864",
            footer_text="Lessan AI · Academic",
        ),
    ),
    DocumentTemplate(
        template_id="business",
        name="Business",
        description="For resumes, cover letters, plans, invoices and client-facing documents.",
        keywords=[
            "business", "commercial", "client", "market", "company",
            "invoice", "quotation", "proposal", "customer", "corporate",
            "meeting", "resume", "cv", "letter", "sales", "marketing",
            "budget", "startup", "pitch",
        ],
        default_kinds=[
            "resume", "cover_letter", "business_plan", "meeting_minutes",
            "letter", "invoice", "quotation",
        ],
        style=StyleSpec(
            heading_color="#1F3864",
            heading_sizes=[15, 13, 12, 12],
            space_after_pt=5,
        ),
    ),
    DocumentTemplate(
        template_id="software_engineering",
        name="Software Engineering",
        description="For SRS, design docs, API references, manuals and technical docs.",
        keywords=[
            "software", "system", "technical", "api", "requirements",
            "specification", "engineering", "developer", "architecture",
            "srs", "code", "manual", "endpoint", "deployment", "database",
            "frontend", "backend", "release", "user guide",
        ],
        default_kinds=[
            "software_requirements", "software_design", "api_documentation",
            "user_manual", "technical_documentation",
        ],
        style=StyleSpec(
            mono_family="Consolas",
            heading_color="#24478F",
            heading_sizes=[15, 13, 12, 11],
        ),
    ),
    DocumentTemplate(
        template_id="legal",
        name="Legal",
        description="For contracts, agreements and compliance documents.",
        keywords=[
            "legal", "contract", "law", "agreement", "compliance",
            "regulation", "clause", "liability", "terms", "policy",
            "warranty", "confidential", "indemnity",
        ],
        style=StyleSpec(
            heading_color="#7B1E26",
            footer_text="Lessan AI · Legal",
        ),
    ),
    DocumentTemplate(
        template_id="research",
        name="Research",
        description="For experiments, surveys, findings and technical studies.",
        keywords=[
            "experiment", "data", "findings", "laboratory", "survey",
            "hypothesis", "participants", "methodology", "sample",
            "quantitative", "qualitative", "statistics",
        ],
        style=StyleSpec(
            heading_color="#20534D",
            footer_text="Lessan AI · Research",
        ),
    ),
    DocumentTemplate(
        template_id="corporate",
        name="Corporate",
        description="For reports, presentations, strategy and executive documents.",
        keywords=[
            "corporate", "annual", "strategy", "executive", "stakeholder",
            "board", "report", "kpi", "financial", "quarterly", "governance",
            "audit", "presentation",
        ],
        default_kinds=["report", "project_report", "presentation"],
        style=StyleSpec(
            heading_color="#1F3864",
            heading_sizes=[16, 14, 12, 12],
        ),
    ),
    DocumentTemplate(
        template_id="generic",
        name="Generic",
        description="Safe default profile used when nothing else matches.",
        keywords=[],
        style=StyleSpec(),
    ),
]


class DocumentTemplateManager:
    """Registry + selection logic for document templates."""

    def __init__(self) -> None:
        self._templates: Dict[str, DocumentTemplate] = {}
        for template in _BUILTIN_TEMPLATES:
            self.register(template)

    def register(self, template: DocumentTemplate) -> DocumentTemplate:
        self._templates[template.template_id] = template
        return template

    def unregister(self, template_id: str) -> bool:
        return self._templates.pop(template_id, None) is not None

    def get(self, template_id: Optional[str]) -> Optional[DocumentTemplate]:
        if not template_id:
            return None
        template = self._templates.get(template_id)
        if template is None:
            # Fuzzy id match (e.g. "software" → "software_engineering").
            lowered = template_id.strip().lower()
            for candidate in self._templates.values():
                if lowered in candidate.template_id or candidate.template_id in lowered:
                    return candidate
        return template

    def all(self) -> List[DocumentTemplate]:
        return list(self._templates.values())

    def default_for(self, kind_default: Optional[str]) -> Optional[DocumentTemplate]:
        return self.get(kind_default)

    def select(
        self,
        explicit: Optional[str] = None,
        kind_default: Optional[str] = None,
        text: Optional[str] = None,
    ) -> DocumentTemplate:
        """Select a template.

        Args:
            explicit: User-provided template id (highest priority).
            kind_default: The resolved document type's ``default_template``.
            text: Free-form request text used for keyword scoring.
        """
        generic = self._templates["generic"]

        if explicit:
            template = self.get(explicit)
            if template is not None:
                return template

        if kind_default:
            template = self.get(kind_default)
            if template is not None:
                return template

        haystack = (text or "").lower()
        best, best_score = generic, 0
        for template in self._templates.values():
            if template is generic:
                continue
            score = sum(haystack.count(kw) for kw in template.keywords if kw)
            if score > best_score:
                best, best_score = template, score
        return best

    def summary(self) -> str:
        return "\n".join(
            f"- {t.template_id}: {t.name} — {t.description}" for t in self._templates.values()
        )


