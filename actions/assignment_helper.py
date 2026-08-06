# actions/assignment_helper.py
# Lessan AI — Assignment Assistant
#
# Helps with academic/professional assignments:
#   - Research & Summarization
#   - Drafting & Outlining
#   - Code Explanation & Debugging
#   - Citation Formatting (APA, MLA, etc.)
#   - Math/Logic Problem Solving
#   - Deep document analysis + editable PDF output (when a PDF is attached)

import datetime
from pathlib import Path

def assignment_helper(parameters: dict, player=None, speak=None) -> str:
    """
    Assists with assignments.

    Parameters:
        task: str (required) — e.g., "outline", "draft", "explain", "solve", "cite",
                               "deep", "analyze", "edit"
        subject: str (required) — e.g., "History", "Python Programming", "Calculus"
        details: str (required) — the assignment prompt or problem (or the edit
                                  instruction when task=edit / deep mode)
        format: str (optional) — e.g., "APA", "MLA"
        file_path: str (optional) — path to an uploaded PDF. When provided with
                                    task=deep/analyze/edit (or details describing
                                    an edit), routes to the deep analysis + editable
                                    PDF pipeline.
        rubric: str (optional) — assignment requirements to grade against
        deep: bool (optional) — run the multi-pass deep analysis instead of a
                                single response (works without a PDF too)
        save: bool (optional) — save report (default: True)
    """
    task      = (parameters.get("task") or "").lower().strip()
    subject   = (parameters.get("subject") or "").strip()
    details   = (parameters.get("details") or "").strip()
    fmt       = (parameters.get("format") or "standard").strip()
    file_path = (parameters.get("file_path") or parameters.get("pdf_path") or "").strip()
    rubric    = (parameters.get("rubric") or "").strip()
    deep      = bool(parameters.get("deep", False))

    # ── PDF attached → deep analysis + editable PDF pipeline ──────────────
    if file_path:
        pdf = Path(file_path)
        if not pdf.exists() or pdf.suffix.lower() != ".pdf":
            return f"📄 File not found or not a PDF: {file_path}"

        from actions.pdf_editor import pdf_editor

        # Determine mode from task/details
        task_l = (task + " " + details).lower()
        has_edit_word = any(w in task_l for w in
                            ("edit", "rewrite", "fix", "improve", "correct",
                             "shorten", "expand", "summarise", "summarize",
                             "polish", "add ", "remove ", "make ", "change",
                             "convert to ", "format"))
        if has_edit_word:
            mode = "both" if (task in ("deep", "analyze", "analyze+edit") or deep) else "edit"
            instruction = details or (
                "Improve grammar, clarity, and academic style while preserving "
                "the author's ideas and intent."
            )
        else:
            mode     = "analyze"
            instruction = ""

        return pdf_editor(
            {
                "file_path":  str(pdf),
                "mode":       mode,
                "instruction": instruction,
                "rubric":     rubric,
                "save":       parameters.get("save", True),
                "subject":    subject,
            },
            player=player,
            speak=speak,
        )

    if not task or not subject or not details:
        return "Please provide task, subject, and details."

    # ── Text-only deep analysis mode ───────────────────────────────────────
    if task in ("deep", "analyze", "analyz", "grammar check", "edit") or deep:
        from actions.pdf_editor import deep_analyze_text
        try:
            if task == "edit" or deep:
                # text + edit instruction → return both analysis and rewritten text
                edited = deep_analyze_text(details, rubric, instruction="", save=False)
                from omniroute import client
                rewritten = client.chat(
                    f"Rewrite the following text per this instruction: {details}\n\n"
                    f"Apply the instruction literally to the text below. "
                    f"Output only the rewritten text.\n\nText:\n{details}",
                    system="You are a professional editor. Output only the rewritten text.",
                    temperature=0.3,
                )
                return f"🎓 **Deep Analysis**\n\n{edited}\n\n✏️ **Rewritten**\n\n{rewritten}"
            return deep_analyze_text(details, rubric, instruction="",
                                     save=parameters.get("save", True))
        except Exception as e:
            return f"❌ Deep analysis failed: {e}"

    # ── Standard single-response mode ──────────────────────────────────────
    try:
        from omniroute import client
        
        system_msg = (
            f"You are an expert academic tutor specializing in {subject}. "
            "Provide clear, accurate, and helpful guidance. "
            "If the task is to solve a problem, explain the steps clearly. "
            "If it's writing, provide a high-quality draft or outline."
        )
        
        prompt = (
            f"Task: {task}\n"
            f"Subject: {subject}\n"
            f"Format: {fmt}\n"
            f"Details/Prompt:\n{details}\n\n"
            "Provide a comprehensive response."
        )
        
        result = client.chat(prompt, system=system_msg)
        
        # Save to reports
        reports_dir = Path.home() / "Lessan" / "reports" / "assignments"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        save_path = reports_dir / f"{subject.replace(' ', '_')}-{task}-{stamp}.md"
        
        report_content = f"# Assignment Help: {subject}\n"
        report_content += f"**Task:** {task}\n"
        report_content += f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        report_content += "## Response\n\n"
        report_content += result
        
        save_path.write_text(report_content, encoding="utf-8")
        
        return f"🎓 **Assignment Help Generated**\n\n{result}\n\n📄 Saved to: {save_path}"

    except Exception as e:
        return f"❌ Assignment helper failed: {e}"