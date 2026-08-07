"""
Multi-agent project-building orchestrator for Lessan AI.

This is the application-layer consumer the ``lessan_ai_agents``
framework's package docstring anticipated: it wires the public
framework interfaces together and sequences real work through them.
Nothing in the framework knows about it; it only talks to the public
API (AgentRegistry, AgentManager, InMemoryTaskQueue,
InProcessCommunicationBus, InMemoryAgentMemory, the eleven RoleAgents).

``build_project`` replaces the monolithic ``actions/dev_agent.py`` loop
while keeping the ``dev_agent`` tool's interface and behaviour: plan
the project, write real files, install dependencies, open VSCode, run,
and fix errors — but now each stage is delegated to a role agent the
way a product team would work:

    1. CEOAgent               delegates the objective to the specialists
    2. ProductManagerAgent    scopes the feature + acceptance criteria
    3. SolutionArchitectAgent produces the file plan (entry point,
                               module list, run command, dependencies)
    4. DatabaseEngineerAgent  proposes a schema (data-heavy projects)
    5. UIDesignerAgent        proposes layout guidance (frontend/web)
    6. Frontend/Backend EngineerAgents write every file (dependency
       order, imports matched to the actual structure)
    7. Project is installed, opened in VSCode, and executed
    8. On failure: QAEngineerAgent + SecurityEngineerAgent review the
       error, then the engineer agents produce the fix (max
       ``MAX_FIX_ATTEMPTS``)
    9. DevOpsEngineerAgent    outlines release/packaging steps
    10. DocumentationEngineerAgent writes the project README

Every agent runs with an injectable ``executor`` (``prompt -> str``,
see ``lessan_ai_agents.execution.llm_backend``) so tests can use a fake
and production can use the real LLM backend without any code change.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from lessan_ai_agents.agents import build_default_roster
from lessan_ai_agents.core.agent_manager import AgentManager
from lessan_ai_agents.core.agent_registry import AgentRegistry
from lessan_ai_agents.core.base_agent import AgentResult
from lessan_ai_agents.core.communication import InProcessCommunicationBus
from lessan_ai_agents.core.memory import InMemoryAgentMemory
from lessan_ai_agents.core.task_queue import InMemoryTaskQueue, Task
from lessan_ai_agents.execution.llm_backend import (
    default_executor,
    parse_json_response,
    strip_fences,
)

# Where generated projects live (same convention as actions/dev_agent.py).
# Override via the LESSAN_PROJECTS_DIR environment variable.
PROJECTS_DIR = Path(os.getenv("LESSAN_PROJECTS_DIR", str(Path.home() / "Lessan" / "projects")))

# How many run → diagnose → fix rounds before giving up.
MAX_FIX_ATTEMPTS = 5

# Languages whose files are written by the Frontend Engineer agent.
_FRONTEND_LANGS = frozenset(
    {
        "html",
        "css",
        "javascript",
        "typescript",
        "js",
        "ts",
        "web",
        "frontend",
        "react",
        "vue",
        "svelte",
    }
)

# Lower-case substrings that suggest a project needs persistence guidance.
_DB_HINTS = (
    "database",
    "store",
    "persist",
    "sql",
    "user data",
    "records",
    "backend api",
    "save",
    "storage",
)

_AGENT_NAMES = (
    "CEOAgent",
    "ProductManagerAgent",
    "SolutionArchitectAgent",
    "UIDesignerAgent",
    "FrontendEngineerAgent",
    "BackendEngineerAgent",
    "DatabaseEngineerAgent",
    "QAEngineerAgent",
    "SecurityEngineerAgent",
    "DevOpsEngineerAgent",
    "DocumentationEngineerAgent",
)


# ────────────────────────────────────────────────────────────────────
# Framework wiring helpers
# ────────────────────────────────────────────────────────────────────

def _log(msg: str, player: Any = None) -> None:
    print(f"[DevAgents] {msg}")
    if player is not None and hasattr(player, "write_log"):
        try:
            player.write_log(f"[DevAgents] {msg}")
        except Exception:
            pass


def _boot_framework(exec_fn: Callable[[str], str]) -> AgentManager:
    """Instantiate the full framework (memory, bus, roster, registry,
    manager) with every role agent wired to ``exec_fn``."""
    memory = InMemoryAgentMemory()
    bus = InProcessCommunicationBus()
    roster = build_default_roster(memory=memory, communication_bus=bus)
    for agent in roster:
        agent.executor = exec_fn
    registry = AgentRegistry()
    for agent in roster:
        registry.register(agent)
    manager = AgentManager(registry, InMemoryTaskQueue(), communication_bus=bus)
    return manager


def _dispatch(
    manager: AgentManager,
    agent_name: str,
    payload: dict,
    prompt: Optional[str] = None,
) -> AgentResult:
    """Enqueue one task targeting ``agent_name`` and dispatch it through
    the framework immediately (the orchestrator drives a strict sequence,
    one team member at a time)."""
    if agent_name not in _AGENT_NAMES:
        raise ValueError(f"Unknown agent '{agent_name}'. Registered: {_AGENT_NAMES}")
    task_payload = dict(payload)
    if prompt is not None:
        task_payload["prompt"] = prompt
    task = Task(
        title=f"{agent_name}: {task_payload.get('task_id', 'work item')}",
        target_agent=agent_name,
        payload=task_payload,
    )
    manager.submit(task)
    result = manager.dispatch_next()
    if result is None:
        raise RuntimeError(f"Agent '{agent_name}' did not return a result.")
    if not result.success:
        raise RuntimeError(f"Agent '{agent_name}' failed: {result.error}")
    return result


def _agent_output(result: AgentResult) -> str:
    """Extract the executor's text output from an AgentResult envelope."""
    output = result.output
    if isinstance(output, dict):
        return output.get("output", "")
    return str(output or "")


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "429",
            "rate limit",
            "resource_exhausted",
            "quota",
            "too many requests",
        )
    )




# ────────────────────────────────────────────────────────────────────
# Project runtime utilities (ported from actions/dev_agent.py so the
# orchestrator stays self-contained and avoids a circular import).
# ────────────────────────────────────────────────────────────────────

def _run_project(run_command: str, project_dir: Path, timeout: int = 30) -> str:
    _log(f"🚀 Running: {run_command}")
    try:
        parts = run_command.split()
        if parts and parts[0].lower() == "python":
            parts[0] = sys.executable
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(project_dir),
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        combined_parts = []
        if stdout:
            combined_parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            combined_parts.append(f"STDERR:\n{stderr}")
        return "\n\n".join(combined_parts) if combined_parts else "Ran with no output."
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s — long-running app (server/GUI) is likely working."
    except FileNotFoundError as exc:
        return f"Command not found: {exc}"
    except Exception as exc:
        return f"Run error: {exc}"


def _install_dependencies(dependencies: list[str], project_dir: Path) -> str:
    if not dependencies:
        return "No external dependencies."
    to_install: list[str] = []
    for dep in dependencies:
        pkg_name = re.split(r"[>=<!]", dep)[0].strip()
        check = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg_name],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            to_install.append(dep)
        else:
            _log(f"✓ Already installed: {pkg_name}")
    if not to_install:
        return f"All dependencies already installed: {', '.join(dependencies)}"
    _log(f"📦 Installing: {to_install}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + to_install,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=str(project_dir),
        )
        if result.returncode == 0:
            return f"Installed: {', '.join(to_install)}"
        return f"Install warning (non-fatal): {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "Dependency install timed out (non-fatal)."
    except Exception as exc:
        return f"Install error (non-fatal): {exc}"


def _try_auto_install(error_output: str, project_dir: Path) -> bool:
    """If the run failed with ModuleNotFoundError, try installing the
    missing package so the fix loop can make progress."""
    pattern = re.compile(r"No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]", re.IGNORECASE)
    match = pattern.search(error_output)
    if not match:
        return False
    pkg = match.group(1).replace("_", "-").split(".")[0]
    _log(f"🔧 Auto-installing missing package: {pkg}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(project_dir),
        )
        return result.returncode == 0
    except Exception:
        return False


def _open_vscode(project_dir: Path) -> bool:
    vscode_candidates = [
        "code",
        rf"C:\Users\{Path.home().name}\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
    ]
    for cmd in vscode_candidates:
        try:
            subprocess.Popen(
                [cmd, str(project_dir)],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            _log(f"💻 VSCode opened: {project_dir}")
            return True
        except Exception:
            continue
    return False


def _classify_error(output: str) -> str:
    low = output.lower()
    if any(x in low for x in ("no module named", "modulenotfounderror", "importerror")):
        return "dependency_error"
    if "syntaxerror" in low or "invalid syntax" in low:
        return "syntax_error"
    if "cannot import" in low:
        return "import_error"
    if any(
        x in low
        for x in (
            "traceback",
            "exception",
            "error:",
            "nameerror",
            "typeerror",
            "attributeerror",
            "valueerror",
            "keyerror",
            "indexerror",
            "zerodivisionerror",
            "filenotfounderror",
            "permissionerror",
        )
    ):
        return "runtime_error"
    return "none"


def _has_error(output: str) -> bool:
    if not output or not output.strip():
        return False
    if "timed out" in output.lower() or "long-running app" in output.lower():
        return False
    return _classify_error(output) != "none"


def _parse_traceback(
    output: str, project_files: list[str]
) -> tuple[Optional[str], Optional[int]]:
    pattern = re.compile(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', re.IGNORECASE)
    matches = pattern.findall(output)
    for raw_path, line_str in reversed(matches):
        raw_name = Path(raw_path).name
        for project_file in project_files:
            if (
                Path(project_file).name == raw_name
                or project_file == raw_path
                or raw_path.endswith(project_file)
            ):
                return project_file, int(line_str)
    return None, None


def _is_frontend_file(path: str, language: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in {".html", ".css", ".jsx", ".tsx", ".vue", ".svelte"}:
        return True
    if ext in {".js", ".ts"} and language.lower() in _FRONTEND_LANGS:
        return True
    return False


def _files_to_fix(
    error_file: Optional[str],
    error_type: str,
    entry_point: str,
    all_files: list[dict],
) -> list[str]:
    files_to_fix: list[str] = []
    if error_file:
        files_to_fix.append(error_file)
        if error_type == "import_error":
            for fi in all_files:
                if error_file.replace("/", ".").replace(".py", "") in fi.get("imports", []):
                    p = fi["path"]
                    if p not in files_to_fix:
                        files_to_fix.append(p)
    else:
        files_to_fix.append(entry_point)
    return files_to_fix



# ────────────────────────────────────────────────────────────────────
# Role-specific prompt builders (fed to the agents via the payload's
# "prompt" override so each agent's identity still routes the work).
# ────────────────────────────────────────────────────────────────────

def _plan_prompt(description: str, language: str) -> str:
    return f"""You are the Solution Architect Agent for Lessan AI.
You are planning a brand new project. Return ONLY valid JSON. No markdown fences, no extra text, no explanation.

JSON schema (all fields required):
{{
  "project_name": "short_snake_case_name",
  "entry_point": "path to the main runnable file",
  "files": [
    {{"path": "relative/path/to/file.py", "description": "what this module does", "imports": ["module.or.file.imported"]}}
  ],
  "run_command": "command to run the project from the project root (e.g. python main.py)",
  "dependencies": ["pip/package names the project needs, or []"]
}}

Project request: {description}
Programming language: {language}

Rules:
- {language} project, all file paths relative to the project root.
- "entry_point" and "run_command" must agree with each other.
- Every file the project needs must be listed — never reference a file that is not in "files".
- Keep the project small and self-contained.
- Use only well-known, stable dependencies; prefer the standard library when possible.
- imports must be exact module paths for the project's own files (e.g. "utils.helpers").
- Return ONLY the JSON object."""


def _codegen_rules(language: str) -> str:
    low = language.lower()
    if low in ("javascript", "typescript", "js", "ts"):
        return (
            "- Use ES6+ module syntax where appropriate; no missing imports.\n"
            "- The entry file must actually start the app (listen on a port, print output, etc.)."
        )
    return (
        "- Use proper error handling (try/except) where I/O or network calls are made.\n"
        "- Add `if __name__ == '__main__':` to the entry file so it runs directly."
    )


def _write_file_prompt(
    file_info: dict,
    all_files: list[dict],
    project_description: str,
    language: str,
    file_codes: dict[str, str],
) -> str:
    file_path = file_info.get("path", "")
    imports = file_info.get("imports", [])
    other_ctx = ""
    for fp, code in file_codes.items():
        if code:
            snippet = code[:2000] + ("..." if len(code) > 2000 else "")
            other_ctx += f"\n--- {fp} ---\n{snippet}\n"
    file_list = "\n".join(
        f"  - {f['path']}: {f.get('description', '')}" for f in all_files
    )
    return f"""You are the Frontend/Backend Engineer Agent for Lessan AI. You write production-quality {language} code.

Project goal: {project_description}

All project files:
{file_list}

This file ({file_path}) may import: {', '.join(imports) if imports else '(none)'}

Already-written project files for context (read-only):
{other_ctx[:3500] or "  (none yet — this is the first file)"}

Rules:
- Output ONLY the complete source code for {file_path}. No explanation, no markdown, no backticks.
- The code must work when the project entry point is run from the project root.
- Match import paths EXACTLY to the file paths in the project structure.
- {_codegen_rules(language)}

Code for {file_path}:"""



def _fix_file_prompt(
    fix_path: str,
    current_code: str,
    other_ctx: str,
    error_output: str,
    error_type: str,
    line_hint: str,
    project_description: str,
    all_files: list[dict],
    language: str,
) -> str:
    file_list = "\n".join(
        f"  - {f['path']}: {f.get('description', '')}" for f in all_files
    )
    return f"""You are an expert {language} debugger on the Lessan AI agent team. Fix the broken file below.

Project goal: {project_description}

All project files:
{file_list}

Other files for context (read-only — fix only the target file):
{other_ctx[:3500]}

File to fix: {fix_path}{line_hint}
Error type: {error_type}

Error output:
{error_output[:2500]}

Current (broken) code:
{current_code}

Rules:
- Output ONLY the complete fixed code. No explanation, no markdown, no backticks.
- Fix ALL errors visible in the error output.
- Keep all existing correct logic — do not remove working features.
- Ensure import paths match the actual project file structure exactly.
- Do NOT introduce new bugs or remove error handling.

Fixed code for {fix_path}:"""


def _readme_prompt(
    project_name: str,
    description: str,
    language: str,
    files: list[dict],
    run_command: str,
) -> str:
    file_list = "\n".join(
        f"  - {f['path']}: {f.get('description', '')}" for f in files
    )
    return f"""You are the Documentation Engineer Agent for Lessan AI. Write a clean, complete README.md for the generated project below.

Project name: {project_name}
Project goal: {description}
Language: {language}
File structure:
{file_list}
Run command: {run_command}

Output ONLY the README markdown content. No code fences, no extra text.
Include: title, short description, key features, file structure, and install/run instructions."""



# ────────────────────────────────────────────────────────────────────
# The build pipeline
# ────────────────────────────────────────────────────────────────────

def build_project(
    description: str,
    language: str = "python",
    project_name: str = "",
    timeout: int = 30,
    speak: Optional[Callable[[str], None]] = None,
    player: Any = None,
    executor: Optional[Callable[[str], str]] = None,
    projects_dir: Optional[Path] = None,
    open_editor: bool = True,
) -> str:
    """Build a project end-to-end through the multi-agent framework.

    Keeps the same call contract as the legacy ``dev_agent`` tool
    (``description``/``language``/``project_name``/``timeout``/
    ``speak``/``player``) plus two test/CI-friendly knobs:

    - ``executor``: callable ``prompt -> str``. Defaults to Lessan AI's
      LLM backend (Gemini with OmniRoute fallback).
    - ``projects_dir``: where the project directory is created.
    - ``open_editor``: set False to skip opening VSCode (headless/CI).
    """
    description = (description or "").strip()
    if not description:
        return "Please describe the project you want me to build, sir."
    language = (language or "python").strip().lower()
    timeout = max(5, int(timeout))
    exec_fn = executor or default_executor()
    projects_dir = Path(projects_dir) if projects_dir is not None else PROJECTS_DIR

    # 1. Boot the framework and delegate via the CEO.
    manager = _boot_framework(exec_fn)
    _log("CEOAgent: delegating the objective to the specialist team...", player)
    ceo = _dispatch(
        manager,
        "CEOAgent",
        {
            "objective": description,
            "constraints": f"Language: {language}, local-first, zero-subscription build.",
        },
    )
    ceo_direction = _agent_output(ceo)
    _log(f"CEO direction: {ceo_direction[:200]}", player)

    # 2. Product Manager scopes the feature.
    _log("ProductManagerAgent: scoping the feature...", player)
    pm = _dispatch(
        manager,
        "ProductManagerAgent",
        {
            "feature_request": description,
            "user_context": f"Programming language: {language}.",
        },
    )
    feature_spec = _agent_output(pm) or description

    # 3. Solution Architect produces the file plan.
    _log("SolutionArchitectAgent: designing the project structure...", player)
    arch = _dispatch(
        manager,
        "SolutionArchitectAgent",
        {
            "feature_spec": feature_spec,
            "system_constraints": f"Language: {language}, local-first, zero-subscription.",
        },
        prompt=_plan_prompt(description, language),
    )
    try:
        plan = parse_json_response(_agent_output(arch))
    except Exception as exc:
        msg = f"Planning failed, sir: the Solution Architect returned invalid JSON ({exc})."
        if speak:
            speak(msg)
        return msg

    proj_name = re.sub(
        r"[^\w\-]", "_", (project_name or plan.get("project_name") or "lessan_project")
    )
    project_dir = projects_dir / proj_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files = plan.get("files") or []
    if not files:
        msg = "The Solution Architect returned an empty file plan, sir."
        if speak:
            speak(msg)
        return msg
    entry_point = plan.get("entry_point", "main.py")
    run_command = plan.get("run_command") or f"python {entry_point}"
    dependencies = plan.get("dependencies") or []

    # 4. Advisory specialists (only when relevant to the request).
    db_notes = ""
    if any(hint in description.lower() for hint in _DB_HINTS) and language not in (
        "javascript",
        "typescript",
        "js",
        "ts",
    ):
        _log("DatabaseEngineerAgent: proposing a schema...", player)
        db = _dispatch(
            manager,
            "DatabaseEngineerAgent",
            {
                "data_description": description,
                "access_patterns": "Local file / in-memory; zero-subscription execution.",
            },
        )
        db_notes = _agent_output(db)
        _log(f"Database guidance: {db_notes[:150]}", player)

    ui_notes = ""
    if language in _FRONTEND_LANGS:
        _log("UIDesignerAgent: proposing layout guidance...", player)
        ui = _dispatch(
            manager,
            "UIDesignerAgent",
            {
                "design_brief": description,
                "ui_constraints": "Cross-platform web; keep it lightweight.",
            },
        )
        ui_notes = _agent_output(ui)
        _log(f"UI guidance: {ui_notes[:150]}", player)


    # 5. Engineers write every file (dependency order first).
    context_desc = description
    if db_notes:
        context_desc += f"\n\nSchema guidance from the Database Engineer:\n{db_notes[:800]}"
    if ui_notes:
        context_desc += f"\n\nUI guidance from the UI Designer:\n{ui_notes[:800]}"

    file_codes: dict[str, str] = {}
    sorted_files = sorted(files, key=lambda fi: len(fi.get("imports", [])))
    for file_info in sorted_files:
        file_path = file_info.get("path", "")
        if not file_path:
            continue
        agent_name = (
            "FrontendEngineerAgent"
            if _is_frontend_file(file_path, language)
            else "BackendEngineerAgent"
        )
        _log(f"{agent_name}: writing {file_path}...", player)
        write_prompt = _write_file_prompt(
            file_info, files, context_desc, language, file_codes
        )
        try:
            res = _dispatch(
                manager,
                agent_name,
                {
                    "design": context_desc,
                    "affected_modules": "new project",
                    "platforms": "Windows/macOS/Linux",
                },
                prompt=write_prompt,
            )
            code = strip_fences(_agent_output(res))
        except Exception as exc:
            if _is_rate_limit_error(exc):
                msg = "Rate limit reached, sir. Please try again in a moment."
                if speak:
                    speak(msg)
                return msg
            raise
        file_codes[file_path] = code
        full_path = project_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")
        _log(f"✅ Written: {file_path} ({len(code)} chars)", player)
        time.sleep(0.3)

    # 6. Dependencies, editor, then run → diagnose → fix.
    if dependencies:
        _log("Installing dependencies...", player)
        _install_dependencies(dependencies, project_dir)
    if open_editor:
        _open_vscode(project_dir)

    last_output = ""
    succeeded = False
    attempts_used = 0
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        attempts_used = attempt
        last_output = _run_project(run_command, project_dir, timeout)
        _log(f"Output preview: {last_output[:150]}", player)

        if not _has_error(last_output):
            succeeded = True
            break

        if attempt == MAX_FIX_ATTEMPTS:
            break

        error_type = _classify_error(last_output)
        error_file, error_line = _parse_traceback(last_output, list(file_codes.keys()))

        # Missing dependencies are resolved by auto-install rather than a
        # code rewrite, mirroring the legacy builder.
        if error_type == "dependency_error" and _try_auto_install(last_output, project_dir):
            _log("Auto-installed missing dependency — re-running...", player)
            continue

        # 7a. QA and Security review the failure (advisory diagnostics).
        _log(f"QAEngineerAgent: analysing the failure ({error_type})...", player)
        _dispatch(
            manager,
            "QAEngineerAgent",
            {
                "feature_spec": description,
                "acceptance_criteria": f"The project must run without errors. Latest failure:\n{last_output[:2000]}",
            },
        )
        _log("SecurityEngineerAgent: reviewing the fix scope...", player)
        _dispatch(
            manager,
            "SecurityEngineerAgent",
            {
                "component": f"Generated {language} project '{proj_name}'",
                "trust_boundaries": "Local execution only",
            },
        )

        # 7b. The engineer agents produce the fixes.
        files_to_fix = _files_to_fix(error_file, error_type, entry_point, files)
        for fix_path in files_to_fix:
            current_code = file_codes.get(fix_path, "")
            other_ctx = ""
            for fp, code in file_codes.items():
                if fp != fix_path and code:
                    snippet = code[:1500] + ("..." if len(code) > 1500 else "")
                    other_ctx += f"\n--- {fp} ---\n{snippet}\n"
            line_hint = (
                f"\nError appears to be near line {error_line} in this file."
                if error_line and fix_path == error_file
                else ""
            )
            fix_agent = (
                "FrontendEngineerAgent"
                if _is_frontend_file(fix_path, language)
                else "BackendEngineerAgent"
            )
            _log(f"{fix_agent}: fixing {fix_path}...", player)
            fix_prompt = _fix_file_prompt(
                fix_path=fix_path,
                current_code=current_code,
                other_ctx=other_ctx,
                error_output=last_output,
                error_type=error_type,
                line_hint=line_hint,
                project_description=description,
                all_files=files,
                language=language,
            )
            res = _dispatch(
                manager,
                fix_agent,
                {
                    "design": description,
                    "affected_modules": fix_path,
                    "platforms": "Windows/macOS/Linux",
                },
                prompt=fix_prompt,
            )
            fixed = strip_fences(_agent_output(res))
            file_codes[fix_path] = fixed
            full_path = project_dir / fix_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(fixed, encoding="utf-8")
            _log(f"🔧 Fixed: {fix_path}", player)

        time.sleep(1)


    # 8. DevOps outlines release/packaging steps.
    _log("DevOpsEngineerAgent: outlining release steps...", player)
    devops = _dispatch(
        manager,
        "DevOpsEngineerAgent",
        {
            "change_description": f"{description} (built by the Lessan AI agent team)",
            "platforms": "Windows/macOS/Linux",
        },
    )
    release_notes = _agent_output(devops)

    # 9. Documentation writes the README.
    _log("DocumentationEngineerAgent: writing README...", player)
    doc = _dispatch(
        manager,
        "DocumentationEngineerAgent",
        {
            "change_description": description,
            "audience": "End users and developers",
        },
        prompt=_readme_prompt(proj_name, description, language, files, run_command),
    )
    readme = strip_fences(_agent_output(doc))
    (project_dir / "README.md").write_text(readme, encoding="utf-8")
    _log(f"✅ Written: README.md ({len(readme)} chars)", player)

    if succeeded:
        msg = (
            f"Project '{proj_name}' is working, sir. Built by the agent team "
            f"in {attempts_used} attempt{'s' if attempts_used > 1 else ''}. "
            f"Saved to: {project_dir}\n\n"
            f"Release/packaging plan:\n{release_notes[:500]}"
        )
        if speak:
            speak(msg)
        return f"{msg}\n\nOutput:\n{last_output}"

    msg = (
        f"I couldn't fully fix '{proj_name}' after {MAX_FIX_ATTEMPTS} attempts, sir. "
        f"The project is saved at {project_dir} — open it in VSCode and check manually.\n\n"
        f"Release/packaging plan:\n{release_notes[:500]}"
    )
    if speak:
        speak(msg)
    return f"{msg}\n\nLast error:\n{last_output[:600]}"

