"""Document type taxonomy for Lessan AI.

:class:`DocumentTypeRegistry` maps free-form user requests ("make a proposal
for our new API", "draft my CV") onto a known :class:`DocumentType` via
explicit ids, aliases and name matching. Each type carries a suggested
section schema (the backbone used for AI generation *and* for the offline
skeleton fallback), plus presentation flags (TOC, title page) and a default
template id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DocumentType:
    """A supported class of professional document."""

    type_id: str
    name: str
    description: str
    aliases: List[str]
    schema: List[str] = field(default_factory=list)
    default_template: str = "generic"
    toc: bool = True
    title_page: bool = True
    instructions: str = ""
    default_format: str = "docx"


_BUILTIN_TYPES: List[DocumentType] = [
    DocumentType(
        type_id="research_proposal",
        name="Research Proposal",
        description="A formal proposal outlining research objectives, methodology and timeline.",
        aliases=["research proposal", "proposal", "grant proposal"],
        default_template="academic",
        schema=[
            "Title and Abstract", "Background", "Research Question",
            "Literature Review", "Methodology", "Timeline",
            "Expected Outcomes", "Budget and Resources", "References",
        ],
        instructions=(
            "Separate objectives from methodology. Include a realistic "
            "timeline and concrete deliverables."
        ),
    ),
    DocumentType(
        type_id="thesis",
        name="Thesis",
        description="A long-form academic dissertation with a rigorous structure.",
        aliases=["thesis", "dissertation"],
        default_template="academic",
        schema=[
            "Abstract", "Introduction", "Literature Review", "Methodology",
            "Findings", "Discussion", "Conclusion", "References",
        ],
    ),
    DocumentType(
        type_id="resume",
        name="Resume / CV",
        description="A concise professional resume or curriculum vitae.",
        aliases=["resume", "cv", "curriculum vitae"],
        default_template="business",
        toc=False,
        title_page=False,
        schema=[
            "Contact Information", "Professional Summary", "Core Skills",
            "Professional Experience", "Education", "Certifications", "References",
        ],
        instructions=(
            "Use concise bullet points. Quantify achievements where possible. "
            "Omit 'References available upon request'."
        ),
    ),
    DocumentType(
        type_id="cover_letter",
        name="Cover Letter",
        description="A one-page motivation letter for a job application.",
        aliases=["cover letter", "covering letter", "motivation letter"],
        default_template="business",
        toc=False,
        title_page=False,
        schema=[
            "Introduction", "Why This Role", "Relevant Experience",
            "Why This Company", "Closing",
        ],
    ),
    DocumentType(
        type_id="business_plan",
        name="Business Plan",
        description="A complete plan covering market, operations and finances.",
        aliases=["business plan", "startup plan"],
        default_template="business",
        schema=[
            "Executive Summary", "Company Overview", "Market Analysis",
            "Products and Services", "Marketing Strategy", "Operations Plan",
            "Financial Plan", "Risk Analysis",
        ],
    ),
    DocumentType(
        type_id="technical_documentation",
        name="Technical Documentation",
        description="User-facing technical documentation for a product or project.",
        aliases=["technical documentation", "technical report"],
        default_template="software_engineering",
        schema=[
            "Overview", "Architecture", "Installation", "Configuration",
            "Usage", "Troubleshooting", "FAQ",
        ],
    ),
    DocumentType(
        type_id="software_requirements",
        name="Software Requirements",
        description="A Software Requirements Specification (SRS).",
        aliases=[
            "srs", "software requirements specification", "software requirements",
            "requirements document", "requirements specification",
            "functional specification",
        ],
        default_template="software_engineering",
        schema=[
            "Introduction", "Scope", "Functional Requirements",
            "Non-Functional Requirements", "User Stories", "Constraints",
            "Acceptance Criteria", "Future Scope",
        ],
    ),
    DocumentType(
        type_id="software_design",
        name="Software Design",
        description="A software design document describing architecture and components.",
        aliases=[
            "software design document", "software design", "design document",
            "sdd", "system design",
        ],
        default_template="software_engineering",
        schema=[
            "Overview", "Architecture", "Component Design", "Data Model",
            "APIs and Interfaces", "Error Handling", "Testing Strategy",
            "Deployment",
        ],
    ),
    DocumentType(
        type_id="project_report",
        name="Project Report",
        description="A status or completion report for a project.",
        aliases=["project report", "progress report", "status report"],
        default_template="corporate",
        schema=[
            "Executive Summary", "Objectives", "Progress", "Achievements",
            "Issues and Risks", "Next Steps", "Conclusion",
        ],
    ),
    DocumentType(
        type_id="meeting_minutes",
        name="Meeting Minutes",
        description="Structured minutes capturing decisions and action items.",
        aliases=["meeting minutes", "minutes of meeting", "minutes", "meeting notes"],
        default_template="business",
        toc=False,
        schema=[
            "Attendees", "Agenda", "Discussion", "Decisions",
            "Action Items", "Next Meeting",
        ],
    ),
    DocumentType(
        type_id="user_manual",
        name="User Manual",
        description="An end-user guide for a product.",
        aliases=["user manual", "user guide", "manual", "user documentation"],
        default_template="software_engineering",
        schema=[
            "Introduction", "Installation", "Getting Started", "Features",
            "Procedures", "Troubleshooting", "Support",
        ],
    ),
    DocumentType(
        type_id="api_documentation",
        name="API Documentation",
        description="Reference documentation for a public API.",
        aliases=["api documentation", "api docs", "api reference"],
        default_template="software_engineering",
        schema=[
            "Overview", "Authentication", "Endpoints", "Request and Response",
            "Error Codes", "Rate Limits", "Examples", "Changelog",
        ],
    ),
    DocumentType(
        type_id="presentation",
        name="Presentation",
        description="A structured slide deck (outline, agenda, key points).",
        aliases=["presentation", "slide deck", "slides", "deck"],
        default_template="corporate",
        toc=False,
        title_page=False,
        schema=[
            "Title", "Agenda", "Key Points", "Supporting Data",
            "Summary", "Next Steps",
        ],
    ),
    DocumentType(
        type_id="letter",
        name="Formal Letter",
        description="A formal business or official letter.",
        aliases=["formal letter", "letter of intent", "official letter", "letter"],
        default_template="business",
        toc=False,
        title_page=False,
        schema=[
            "Recipient", "Subject", "Body", "Closing",
        ],
    ),
    DocumentType(
        type_id="invoice",
        name="Invoice",
        description="An itemised invoice for goods or services.",
        aliases=["invoice", "bill"],
        default_template="business",
        toc=False,
        title_page=False,
        schema=[
            "Seller Details", "Buyer Details", "Invoice Items", "Subtotal and Taxes",
            "Total Due", "Payment Terms",
        ],
        instructions=(
            "Include a line-item table (description, quantity, unit price, "
            "amount), totals and an invoice number in the metadata."
        ),
        default_format="pdf",
    ),
    DocumentType(
        type_id="quotation",
        name="Quotation",
        description="A formal price quotation or estimate for a client.",
        aliases=["quotation", "quote", "estimate", "price quote"],
        default_template="business",
        toc=False,
        title_page=False,
        schema=[
            "Seller Details", "Client Details", "Items and Pricing",
            "Terms and Validity", "Acceptance",
        ],
    ),
    DocumentType(
        type_id="report",
        name="General Report",
        description="A general-purpose professional report.",
        aliases=["report", "general report"],
        default_template="corporate",
        schema=[
            "Executive Summary", "Introduction", "Findings",
            "Analysis", "Recommendations", "Conclusion", "References",
        ],
    ),
]


class DocumentTypeRegistry:
    """Holds the supported document types and resolves user requests."""

    def __init__(self) -> None:
        self._types: Dict[str, DocumentType] = {}
        for doc_type in _BUILTIN_TYPES:
            self.register(doc_type)

    def register(self, doc_type: DocumentType) -> DocumentType:
        self._types[doc_type.type_id] = doc_type
        return doc_type

    def unregister(self, type_id: str) -> bool:
        return self._types.pop(type_id, None) is not None

    def get(self, type_id: str) -> Optional[DocumentType]:
        return self._types.get(type_id)

    def resolve(self, query: Optional[str]) -> DocumentType:
        """Resolve a free-form query to a :class:`DocumentType`.

        Order: exact id → alias/name → word-level alias scoring across the
        whole text (longest, most specific alias wins) → name substring →
        general report.
        """
        q = (query or "").strip().lower()
        if not q:
            return self._types["report"]
        if q in self._types:
            return self._types[q]
        for doc_type in self._types.values():
            if q in (a.lower() for a in doc_type.aliases) or q == doc_type.name.lower():
                return doc_type

        # Word-level keyword scoring: single-word aliases match a token in the
        # text, phrase aliases match as a word-bounded substring. Prefer the
        # longest alias so "resume" wins over "cv" and "project report" wins
        # over the generic "report".
        words = set(re.findall(r"[a-z][a-z0-9+.]*", q))
        best: Optional[DocumentType] = None
        best_score = 0
        for doc_type in self._types.values():
            for alias in [doc_type.name, *doc_type.aliases]:
                a = alias.strip().lower()
                if not a:
                    continue
                if " " in a:
                    score = (
                        len(a)
                        if re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", q)
                        else 0
                    )
                else:
                    score = len(a) if a in words else 0
                if score > best_score:
                    best, best_score = doc_type, score
        if best is not None:
            return best

        for doc_type in self._types.values():
            if q in doc_type.name.lower():
                return doc_type
        return self._types["report"]

    def all(self) -> List[DocumentType]:
        return list(self._types.values())

    def summary(self) -> str:
        return "\n".join(
            f"- {t.type_id}: {t.name} — {t.description}" for t in self._types.values()
        )


