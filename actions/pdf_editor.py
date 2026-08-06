"""
pdf_editor.py — Deep Document Analysis & Editable PDF Generator

Features:
  - Extract text from any PDF (text layer via pdfplumber/pypdf, or
    scanned pages via PyMuPDF page rendering + free vision OCR).
  - Deep multi-pass analysis:
      1. Structure pass  — outline, sections, thesis, coherence
      2. Content pass    — arguments, evidence, depth, requirements coverage
      3. Language pass   — grammar, clarity, tone, style
      4. Rubric pass     — grade against user-supplied requirements
      5. Synthesis       — scored report with recommended edits
  - Edit the document with an AI rewrite driven by a natural-language
    instruction ("fix grammar", "add a conclusion", "shorten to 500 words").
  - Render the edited document into a NEW downloadable PDF (reportlab),
    saved to reports/assignments/ and auto-opened in the default viewer.

Entry point follows the Lessan action convention:
    pdf_editor(parameters: dict, player=None, speak=None) -> str
"""

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────

def _reports_dir() -> Path:
    return Path.home() / "Lessan" / "reports" / "assignments"


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _open_file(path: Path):
    """Open a file in the OS default viewer."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def _log(player, msg: str):
    print(f"[PDFEditor] {msg}")
    if player and hasattr(player, "write_log"):
        try:
            player.write_log(msg)
        except Exception:
            pass


def _chunk_text(text: str, size: int = 12000, overlap: int = 800) -> list:
    """Split text into overlapping chunks for context-limited models."""
    text = text.strip()
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            # try to break on a paragraph boundary near the target end
            window = text.rfind("\n\n", start + size // 2, end)
            if window != -1:
                end = window
        chunks.append(text[start:end].strip())
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


# ─────────────────────────────────────────────────────────────────────
# Text extraction
# ─────────────────────────────────────────────────────────────────────

def _extract_text_layer(path: Path, max_chars: int = 200000) -> str:
    """Extract the embedded text layer of a PDF."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception:
        pass

    if not text.strip():
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        except Exception:
            pass
    return text[:max_chars]


def _render_page_images(path: Path, max_pages: int = 10) -> list:
    """Render PDF pages to PNGs (works for scanned/image PDFs)."""
    images = []
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        return images, f"PyMuPDF unavailable for scanned pages: {e}"

    try:
        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=200)
            tmp = Path.home() / "Lessan" / "reports" / "assignments" / f"_page_{i}.png"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(tmp))
            images.append(tmp)
            # keep the first page images on disk for vision; cleanup handled later
        doc.close()
    except Exception as e:
        return [], str(e)
    return images, ""


def _extract_text(path: Path) -> tuple:
    """Full extraction: text layer first, then vision OCR fallback."""
    text = _extract_text_layer(path)
    if text.strip():
        return text, False

    # Scanned / image-based PDF → vision OCR via free routing
    images, err = _render_page_images(path)
    if not images:
        return "", err or "Could not render pages."

    _log(None, "Scanned PDF detected — running vision OCR on pages...")
    from omniroute import client

    ocr_parts = []
    for img in images:
        try:
            page_text = client.vision_from_file(
                "Extract ALL text visible on this page. Preserve paragraph "
                "structure, headings, and bullet points. Return only the text.",
                str(img),
                system="You are an OCR engine. Output only extracted text, nothing else.",
            )
            ocr_parts.append(str(page_text or "").strip())
        except Exception as e:
            ocr_parts.append(f"[OCR failed: {e}]")
        finally:
            try:
                img.unlink()
            except Exception:
                pass
    return "\n\n".join(ocr_parts), True


# ─────────────────────────────────────────────────────────────────────
# Deep multi-pass analysis
# ─────────────────────────────────────────────────────────────────────

_ANALYSIS_SYSTEM = (
    "You are an expert academic reviewer. Analyze documents rigorously, "
    "balance criticism and praise, and always ground every claim in the text. "
    "Be specific and actionable."
)

_PASS_PROMPTS = {
    "structure": (
        "STRUCTURE ANALYSIS\n"
        "Examine the document's organization: thesis/focus, section flow, "
        "paragraph transitions, introduction and conclusion quality. "
        "Identify any missing or weak structural elements.\n\n"
        "Document:\n{text}"
    ),
    "content": (
        "CONTENT ANALYSIS\n"
        "Evaluate the substance: quality of arguments, use of evidence, depth, "
        "relevance to the topic, completeness, and any unsupported claims. "
        "Point out gaps where more detail or evidence is needed.\n\n"
        "Document:\n{text}"
    ),
    "language": (
        "LANGUAGE & STYLE ANALYSIS\n"
        "Check grammar, spelling, punctuation, sentence clarity, tone, word "
        "choice, and academic formality. List the most important errors and "
        "style improvements with short examples.\n\n"
        "Document:\n{text}"
    ),
    "rubric": (
        "REQUIREMENTS / RUBRIC CHECK\n"
        "Grade the document against the following requirements. For each "
        "requirement state whether it is MET, PARTIALLY MET, or NOT MET, "
        "with a one-line justification.\n\n"
        "Requirements:\n{rubric}\n\n"
        "Document:\n{text}"
    ),
}

_SYNTHESIS_PROMPT = """You have just completed a deep multi-pass review of a document.
Below are the findings from each pass:

{passes}

Now produce a synthesis with EXACTLY this structure (markdown):

# Overall Assessment
Score: X/100
Short one-paragraph verdict on the document's overall quality.

## Strengths
- bullet list

## Weaknesses
- bullet list

## Priority Fixes (most impactful first)
1. numbered list of concrete, actionable edits a student can make

## Suggested Rewrite Guidance
Paragraphs describing how the document should be revised to address the fixes above.
"""


def deep_analyze(text: str, rubric: str = "") -> dict:
    """Run the multi-pass analysis and return a structured result."""
    from omniroute import client

    passes = {}
    for key, base_prompt in _PASS_PROMPTS.items():
        # For long docs, analyze the first portion + skip redundancy.
        chunked = _chunk_text(text)
        use = chunked[0]
        if len(chunked) > 1:
            use = (use + "\n\n[...]\n\n" + chunked[1])[:24000]

        prompt = base_prompt.format(text=use, rubric=rubric or "(none provided)")
        try:
            passes[key] = client.chat(prompt, system=_ANALYSIS_SYSTEM)
        except Exception as e:
            passes[key] = f"[{key} pass failed: {e}]"

    synthesis = ""
    try:
        passes_block = "\n\n".join(f"### {k.upper()} PASS\n{v}" for k, v in passes.items())
        synthesis = client.chat(
            _SYNTHESIS_PROMPT.format(passes=passes_block),
            system=_ANALYSIS_SYSTEM,
        )
    except Exception as e:
        synthesis = f"Synthesis failed: {e}"

    score = _extract_score(synthesis)
    return {
        "score": score,
        "passes": passes,
        "synthesis": synthesis,
    }


def _extract_score(text: str) -> int:
    """Pull a X/100 score out of the synthesis text."""
    patterns = [
        r"Score:\s*(\d{1,3})\s*/\s*100",
        r"(\d{1,3})\s*/\s*100",
        r"Score:\s*(\d{1,3})%",
    ]
    for pat in patterns:
        m = re.search(pat, text or "")
        if m:
            try:
                v = int(m.group(1))
                if 0 <= v <= 110:
                    return min(100, v)
            except ValueError:
                pass
    # heuristic fallback: count positive vs negative lines
    neg = len(re.findall(r"(?im)^\s*[-*]\s*(?:weak|error|missing|unclear|improve)", text or ""))
    pos = len(re.findall(r"(?im)^\s*[-*]\s*(?:strong|excellent|clear|well|good)", text or ""))
    return max(0, min(100, 68 + (pos - neg) * 3))


# ─────────────────────────────────────────────────────────────────────
# Editing
# ─────────────────────────────────────────────────────────────────────

_EDIT_SYSTEM = (
    "You are a professional academic editor and writing coach. Rewrite the "
    "document to satisfy the user's instruction exactly. Preserve the author's "
    "ideas, facts, and intent — improve quality, do not invent new content. "
    "Keep the same language as the original unless told otherwise."
)

_EDIT_PROMPT = """Rewrite the document below according to the instruction.

INSTRUCTION:
{instruction}

{guidance}

RULES:
- Output ONLY the rewritten document text. No commentary, no markdown code fences.
- Keep the original structure (headings + paragraphs) unless the instruction changes it.
- Do not add content the original did not support unless the instruction asks for it.
- If you make major additions (e.g. new conclusion), clearly separate them so the
  author can review.

DOCUMENT:
{text}
"""


def edit_document(text: str, instruction: str, analysis: dict = None, rubric: str = "") -> str:
    """AI rewrite of the document per the instruction."""
    from omniroute import client

    guidance = ""
    if analysis and analysis.get("synthesis"):
        guidance = (
            "REVIEW CONTEXT (use this to guide your rewrite):\n"
            + str(analysis["synthesis"])[:12000]
        )

    chunked = _chunk_text(text)
    if len(chunked) == 1:
        prompt = _EDIT_PROMPT.format(instruction=instruction, guidance=guidance, text=text)
        try:
            edited = client.chat(prompt, system=_EDIT_SYSTEM, temperature=0.3)
            return str(edited).strip()
        except Exception as e:
            return f"[Edit failed: {e}]"

    # Long docs: edit each chunk separately, keep continuity markers.
    edited_parts = []
    for i, chunk in enumerate(chunked):
        continuity = (
            f"This is part {i + 1} of {len(chunked)} of the same document. "
            "Continue naturally, keeping consistent style, terminology, and any "
            "section numbering. Do not repeat the beginning of the document.\n\n"
        )
        prompt = _EDIT_PROMPT.format(
            instruction=instruction, guidance=guidance, text=continuity + chunk
        )
        try:
            edited_parts.append(str(client.chat(prompt, system=_EDIT_SYSTEM, temperature=0.3)).strip())
        except Exception as e:
            edited_parts.append(chunk)  # fall back to original section
    return "\n\n".join(edited_parts)


# ─────────────────────────────────────────────────────────────────────
# PDF rendering (reportlab)
# ─────────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)")

_BULLET_RE = re.compile(r"^\s*([-*•]|(\d+)[.)])\s+(.*)")


def _render_pdf(text: str, out_path: Path, title: str = "Edited Document"):
    """Render plain/markdown-ish text into a clean PDF via reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    )

    body_style = ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        textColor=colors.black,
    )
    h1 = ParagraphStyle("H1", parent=body_style, fontName="Helvetica-Bold",
                        fontSize=17, leading=21, spaceBefore=12, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=body_style, fontName="Helvetica-Bold",
                        fontSize=14, leading=18, spaceBefore=10, spaceAfter=6)
    h3 = ParagraphStyle("H3", parent=body_style, fontName="Helvetica-Bold",
                        fontSize=12, leading=16, spaceBefore=8, spaceAfter=5)
    title_style = ParagraphStyle("Title", parent=h1, fontSize=20, leading=25,
                                 alignment=1, spaceAfter=14)

    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    story = [Paragraph(esc(title or "Edited Document"), title_style), Spacer(1, 6)]

    lines = [l.rstrip() for l in text.split("\n")]
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Page-break marker
        if line in ("---", "***") and i + 1 < len(lines):
            story.append(PageBreak())
            i += 1
            continue

        # Headings
        m = _HEADING_RE.match(line)
        if m:
            hashes, content = m.group(1), m.group(2).strip()
            style = {"1": h1, "2": h2, "3": h3}.get(hashes, h3)
            story.append(Paragraph(esc(content), style))
            i += 1
            continue

        # Shouty all-caps short line → treat as heading
        if (1 <= len(line) <= 60 and line.isupper()
                and not line.startswith(("HTTP", "WWW"))):
            story.append(Paragraph(esc(line), h2))
            i += 1
            continue

        # Bullet / numbered list (collect consecutive items)
        m = _BULLET_RE.match(line)
        if m:
            items = []
            while i < len(lines):
                ml = _BULLET_RE.match(lines[i].strip())
                if not ml:
                    break
                bullet_type = ml.group(1)
                content = esc(ml.group(3).strip())
                numbered = bullet_type.isdigit()
                items.append(ListItem(Paragraph(content, body_style),
                                      leftIndent=14, value=0))
                i += 1
            if items:
                if numbered:
                    story.append(ListFlowable(items, bulletType="1",
                                              start=1, leftIndent=18))
                else:
                    story.append(ListFlowable(items, bulletType="bullet",
                                              leftIndent=18, bulletColor=colors.HexColor("#444444")))
                story.append(Spacer(1, 4))
            continue

        # Regular paragraph: gather until a blank line / heading / list
        para_lines = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or _HEADING_RE.match(nxt) or _BULLET_RE.match(nxt):
                break
            para_lines.append(nxt)
            i += 1
        story.append(Paragraph(esc(" ".join(para_lines)), body_style))

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Edited Document",
        author="Lessan AI",
    )
    doc.build(story)


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def pdf_editor(parameters: dict, player=None, speak=None) -> str:
    """
    Deep-analyze and/or edit a PDF document.

    Parameters:
        file_path: str (required) — path to the PDF
        instruction: str (optional) — how to edit, e.g. "fix grammar",
            "add a conclusion", "shorten to 500 words"
        rubric: str (optional) — assignment requirements to grade against
        mode: str (optional) — "analyze" | "edit" | "both" (default: both)
        save: bool (optional) — save analysis report (default: True)
        output_name: str (optional) — base name for the edited PDF
    """
    file_path = (parameters.get("file_path") or parameters.get("pdf_path") or "").strip()
    if not file_path:
        return "No PDF file path provided."

    path = Path(file_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return f"PDF file not found: {file_path}"

    instruction = (parameters.get("instruction") or "").strip()
    rubric      = (parameters.get("rubric") or "").strip()
    mode        = (parameters.get("mode") or "both").lower().strip()
    should_save = bool(parameters.get("save", True))
    out_name    = (parameters.get("output_name") or "").strip()

    if mode not in ("analyze", "edit", "both"):
        return f"Invalid mode '{mode}'. Use analyze, edit, or both."
    if mode in ("edit", "both") and not instruction:
        return "Please provide an 'instruction' describing how to edit the document."

    _log(player, f"📄 Processing {path.name} (mode={mode})")

    reports = _reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()

    # 1. Extract text
    text, is_scanned = _extract_text(path)
    if not text.strip():
        return "Could not extract any text from the PDF (even via OCR). Check the file."

    preview_bits = [f"**Source:** {path.name}", f"**Pages/type:** {'Scanned (OCR)' if is_scanned else 'Text-based'}"
                    f"**Char count:** {len(text):,}"]
    if mode == "edit":
        preview_bits.append(f"**Instruction:** {instruction}")

    summary_parts = ["# PDF Deep Analysis & Edit", ""]
    summary_parts.append("\n".join(preview_bits))
    summary_parts.append("")

    analysis = None

    # 2. Deep analysis
    if mode in ("analyze", "both"):
        _log(player, "🔍 Running deep multi-pass analysis...")
        analysis = deep_analyze(text, rubric)
        summary_parts.append(analysis.get("synthesis", ""))
        summary_parts.append("")

    # 3. Edit
    edited_text = ""
    output_pdf = None
    if mode in ("edit", "both"):
        _log(player, "✏️  Editing document per instruction...")
        analysis_for_edit = analysis if mode == "both" else None
        edited_text = edit_document(text, instruction, analysis_for_edit, rubric)
        if not edited_text or edited_text.startswith("[Edit failed"):
            return f"Document edit failed: {edited_text}"

        base = out_name or f"{path.stem}_edited"
        output_pdf = reports / f"{base}_{stamp}.pdf"
        try:
            _render_pdf(edited_text, output_pdf, title=path.stem)
        except Exception as e:
            # Fallback: save as .md so the work is not lost
            md = reports / f"{base}_{stamp}.md"
            md.write_text(edited_text, encoding="utf-8")
            return (f"⚠️ Edited document saved as text (PDF render failed: {e}).\n"
                    f"Download: {md}")

    # 4. Save analysis report
    if should_save and summary_parts:
        report_path = reports / f"{path.stem}_analysis_{stamp}.md"
        report_path.write_text("\n".join(summary_parts), encoding="utf-8")

    # 5. Compose result message
    msg = []
    if mode in ("analyze", "both") and analysis:
        msg.append(f"🎓 **Deep Analysis Complete**  (Score: {analysis.get('score')}/100)")
        msg.append(analysis.get("synthesis", "")[:1500])
        msg.append("")
        msg.append(f"📄 Analysis report saved: `{report_path}`")

    if output_pdf:
        msg.append("")
        msg.append(f"✅ **Edited PDF ready** — `{output_pdf.name}`")
        msg.append(f"📥 Download: `{output_pdf}`")
        _open_file(output_pdf)

    return "\n".join(msg)


# ─────────────────────────────────────────────────────────────────────
# Text-only deep analysis helper (used by assignment_helper)
# ─────────────────────────────────────────────────────────────────────

def deep_analyze_text(text: str, rubric: str = "", instruction: str = "",
                      save: bool = True) -> str:
    """Deep-analyze arbitrary text (no PDF required). Returns a report string."""
    analysis = deep_analyze(text, rubric)
    report = analysis.get("synthesis", "")
    score = analysis.get("score")

    if save:
        reports = _reports_dir()
        reports.mkdir(parents=True, exist_ok=True)
        stamp = _timestamp()
        report_path = reports / f"deep_analysis_{stamp}.md"
        content = f"# Deep Analysis  —  Score: {score}/100\n\n{report}\n"
        report_path.write_text(content, encoding="utf-8")
        return (f"🎓 **Deep Analysis Complete — Score: {score}/100**\n\n"
                f"{report}\n\n📄 Saved: `{report_path}`")
    return f"🎓 **Deep Analysis Complete — Score: {score}/100**\n\n{report}"