"""AI content generation with a guaranteed offline fallback.

The :class:`ContentGenerator` asks the Model Router for a strict-JSON document
description, parses it into a :class:`DocumentProject`, and — on *any*
failure (unavailable router, exception, unparseable JSON) — retries once and
then falls back to a deterministic :class:`DocumentProject` built from the
resolved document type's schema plus the user's own content. This guarantees
the generator always returns a document.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from core.logging import get_logger

from documents.models import (
    DocumentProject,
    DocumentRequest,
    DocumentSection,
    Paragraph,
    today_str,
)

logger = get_logger("documents.content")

_SYSTEM_PROMPT = (
    "You are an expert professional document writer for Lessan AI. You "
    "produce a single strict JSON object describing a complete, publishable "
    "document. The JSON must be valid, contain no markdown fences, no "
    "commentary and no trailing prose. Every string must be fully written "
    "out (no placeholders, no '[Text here]'). Follow the required section "
    "backbone given by the user, adapting headings and adding subsections "
    "as appropriate."
)

_JSON_BRACKET_RE = re.compile(r"[{\[].*?[}\]]", re.DOTALL)


class ContentGenerator:
    """Generates :class:`DocumentProject` content for a document type."""

    def __init__(self, model_router: Any = None, memory_store: Any = None) -> None:
        self._router = model_router
        self._memory = memory_store

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate(
        self,
        request: DocumentRequest,
        doc_type: Any,
        memory: Optional[Dict[str, Any]] = None,
    ) -> DocumentProject:
        """Generate content, always returning a usable project."""
        if self._router is None:
            return self.build_skeleton(request, doc_type)

        prompt = self._build_prompt(request, doc_type, memory)
        payload = self._request_json(prompt)
        project = self._parse_payload(payload, request, doc_type) if payload else None
        if project is not None:
            return project

        # One repair attempt, then the guaranteed skeleton.
        repair_prompt = prompt + (
            "\n\nYour previous response was not valid JSON. Return ONLY a "
            "single valid JSON object matching the required structure."
        )
        payload = self._request_json(repair_prompt)
        if payload is not None:
            project = self._parse_payload(payload, request, doc_type)
            if project is not None:
                return project

        return self.build_skeleton(request, doc_type)

    def build_skeleton(
        self,
        request: DocumentRequest,
        doc_type: Any,
    ) -> DocumentProject:
        """Deterministic, offline-safe skeleton from the type's schema."""
        schema = list(getattr(doc_type, "schema", None) or [])
        content_paragraphs = _split_paragraphs(request.content)

        sections: List[DocumentSection] = []
        for idx, heading in enumerate(schema):
            section = DocumentSection(heading=heading, level=1)
            if idx == 0:
                section.paragraphs = [
                    Paragraph(text=p) for p in content_paragraphs
                ] or [Paragraph(text="")]
            if heading.lower().startswith("reference"):
                refs = (request.metadata or {}).get("references", [])
                section.references = [r for r in refs if isinstance(r, str)]
            sections.append(section)

        # No schema (should not happen) → one content section.
        if not sections:
            sections.append(
                DocumentSection(
                    heading="Content",
                    paragraphs=[Paragraph(text=p) for p in content_paragraphs],
                )
            )

        topic = request.topic or doc_type.name
        return DocumentProject(
            kind=getattr(doc_type, "type_id", "report"),
            title=topic,
            subtitle="Prepared by Lessan AI",
            author=request.author,
            date=request.date or today_str(),
            sections=sections,
            metadata={"generated_from": "skeleton", "topic": topic},
        )

    # ------------------------------------------------------------------ #
    # Prompt + parsing helpers
    # ------------------------------------------------------------------ #
    def _build_prompt(
        self,
        request: DocumentRequest,
        doc_type: Any,
        memory: Optional[Dict[str, Any]],
    ) -> str:
        schema = "\n".join(f"  {i + 1}. {h}" for i, h in enumerate(doc_type.schema or []))
        guidance = getattr(doc_type, "instructions", "") or ""
        facts = _memory_facts(memory)

        lines = [
            f"Generate a {doc_type.name.lower()} document.",
            "",
            "REQUIRED SECTION BACKBONE (adapt these headings freely, add subsections where useful):",
            schema or "  (no fixed backbone)",
            "",
        ]
        if request.topic:
            lines.append(f"TOPIC: {request.topic}")
        if request.content:
            lines.append(
                "USER CONTENT TO INCORPORATE (rewrite professionally, keep all facts):\n"
                + request.content
            )
        if request.instructions:
            lines.append(f"SPECIFIC INSTRUCTIONS:\n{request.instructions}")
        if guidance:
            lines.append(f"STYLE GUIDANCE FOR THIS DOCUMENT TYPE:\n{guidance}")
        lines.append("FACTS ABOUT THE AUTHOR / CONTEXT:\n" + facts)
        lines.append("")
        lines.append(_SCHEMA_TEMPLATE)
        return "\n".join(lines)

    def _request_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        try:
            response = self._router.complete(
                prompt,
                system=_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.4,
            )
        except Exception as exc:  # noqa: BLE001 - any router failure → fallback
            logger.warning(f"Model router failed during document generation: {exc}")
            return None

        text = _extract_text(response)
        if not text:
            return None
        return _coerce_json(text)

    def _parse_payload(
        self,
        payload: Dict[str, Any],
        request: DocumentRequest,
        doc_type: Any,
    ) -> Optional[DocumentProject]:
        try:
            project = DocumentProject.from_dict(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Malformed AI document JSON: {exc}")
            return None
        if not project.sections:
            logger.warning("AI returned a document with no sections")
            return None
        if not project.title.strip():
            project.title = request.topic or doc_type.name
        project.kind = getattr(doc_type, "type_id", project.kind)
        project.author = project.author or request.author
        project.date = project.date or request.date or today_str()
        project.metadata.setdefault("generated_from", "ai")
        project.metadata.setdefault("topic", request.topic or project.title)
        return project


_SCHEMA_TEMPLATE = """OUTPUT FORMAT — respond with ONLY valid JSON, exactly in this shape:
{
  "title": "Document title",
  "subtitle": "optional subtitle or null",
  "sections": [
    {
      "heading": "Section heading",
      "level": 1,
      "paragraphs": ["A paragraph of professional prose."],
      "bullets": ["Bullet point one.", "Bullet point two."],
      "numbered": ["First step.", "Second step."],
      "tables": [
        {"caption": "optional table caption", "header_row": true, "rows": [["Header A", "Header B"], ["value a1", "value b1"]]}
      ],
      "figure": {"caption": "optional figure caption", "path": null},
      "code": {"language": "python", "text": "def example():\\n    return 42"},
      "references": ["optional reference list for this section"],
      "appendix": false,
      "page_break_after": false
    }
  ],
  "references": ["optional global reference list"],
  "metadata": {"invoice_number": "INV-0001"}
}
Make the document as complete and detailed as the topic requires."""


def _extract_text(response: Any) -> Optional[str]:
    if response is None:
        return None
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else None


def _coerce_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON extraction from a model response."""
    text = text.strip()
    # Strip code fences if the model wrapped the JSON.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    # Last resort: slice the outermost JSON-ish block.
    for match in _JSON_BRACKET_RE.finditer(text):
        candidate = match.group(0)
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _split_paragraphs(content: Optional[str]) -> List[str]:
    if not content:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]


def _memory_facts(memory: Optional[Dict[str, Any]]) -> str:
    if not memory:
        return "No prior facts available."
    interesting = (
        "name", "contact", "email", "phone", "company", "education",
        "degree", "title", "role", "address", "organisation", "organization",
    )
    lines: List[str] = []
    for key in sorted(memory, key=str):
        if any(tag in str(key).lower() for tag in interesting):
            value = memory[key]
            if isinstance(value, dict):
                value = value.get("value", value)
            text = str(value)[:300]
            if text.strip():
                lines.append(f"- {key}: {text}")
    return "\n".join(lines) if lines else "No prior facts available."


