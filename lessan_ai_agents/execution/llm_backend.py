"""
LLM execution backend for the lessan_ai_agents framework.

Provides the injectable ``executor`` callables (``prompt -> str``) that
turn an agent's rendered prompt into real output. ``RoleAgent`` accepts
an ``executor``; when one is provided ``_run`` calls it and returns its
output. Without an executor, agents keep their architecture-only stub
behaviour, so the framework remains inert and dependency-free on its
own.

The default executor reuses Lessan AI's existing LLM access patterns
(no new dependencies):

1. ``omniroute.client`` (the free-model OpenRouter router with auto
   rate-limit rotation) — the fast, free, rate-limit-resilient path, and
2. ``google.generativeai`` with the API key in ``config/api_keys.json``
   (the same path ``actions/dev_agent.py`` uses) as the fallback.

The backend order is controlled by the ``LESSAN_LLM_BACKEND`` env var:

- ``omniroute`` (default): free OpenRouter pool first, Gemini last
  resort. Best for development — free and fast, never blocked by the
  Gemini free-tier quota.
- ``auto``: Gemini first, OmniRoute fallback (previous behaviour).
- ``gemini``: Gemini only.

Gemini also gets a per-process cooldown after a rate-limit hit, so a
quota-slammed free tier is skipped entirely for ``GEMINI_RATE_LIMIT_
COOLDOWN`` seconds instead of being retried (and failing) on every call.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional

# A prompt executor: render a prompt string, return the model's text.
Executor = Callable[[str], str]

GEMINI_MODEL = "gemini-2.5-flash"

# Per-process cooldown for the Gemini backend after a rate-limit hit.
# Once tripped, Gemini is skipped entirely until this window elapses, so
# dev loops don't burn a guaranteed-to-fail Gemini call on every prompt.
GEMINI_RATE_LIMIT_COOLDOWN = 60.0  # seconds
_gemini_cooled_until: float = 0.0


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def _load_gemini_api_key() -> str:
    key_path = _base_dir() / "config" / "api_keys.json"
    try:
        data = json.loads(key_path.read_text(encoding="utf-8"))
        return str(data.get("gemini_api_key") or "").strip()
    except Exception:
        return ""


def strip_fences(text: str) -> str:
    """Remove ```...``` code fences (and an optional language tag) from a
    model response, leaving only the payload."""
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9_\-]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def parse_json_response(text: str) -> dict:
    """Best-effort parse of a model response into a dict.

    Tolerates code fences, a leading ``json`` marker, and stray prose
    before/after the outermost JSON object.
    """
    clean = strip_fences(text or "")
    if clean.lower().startswith("json"):
        clean = clean[4:].lstrip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start, end = clean.find("{"), clean.rfind("}")
        if start >= 0 and end > start:
            return json.loads(clean[start : end + 1])
        raise


def make_gemini_executor(model: str = GEMINI_MODEL) -> Executor:
    """Return an executor backed by ``google.generativeai`` (same access
    pattern as ``actions/dev_agent.py``). Raises ``RuntimeError`` if no
    Gemini API key is configured."""

    def _execute(prompt: str) -> str:
        api_key = _load_gemini_api_key()
        if not api_key:
            raise RuntimeError("No gemini_api_key in config/api_keys.json.")
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        response = genai.GenerativeModel(model).generate_content(prompt)
        return response.text

    return _execute


def make_omniroute_executor() -> Executor:
    """Return an executor backed by ``omniroute.client`` (Lessan's
    free-model OpenRouter router with auto rate-limit rotation)."""

    def _execute(prompt: str) -> str:
        from omniroute import client

        return client.chat(prompt)

    return _execute


def _is_rate_limit_error(exc: Exception) -> bool:
    """True if an exception smells like an LLM provider rate limit."""
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


def _gemini_on_cooldown() -> bool:
    return time.time() < _gemini_cooled_until


def _mark_gemini_rate_limited() -> None:
    global _gemini_cooled_until
    _gemini_cooled_until = time.time() + GEMINI_RATE_LIMIT_COOLDOWN
    print(
        f"[llm_backend] Gemini rate-limited — cooling down "
        f"{int(GEMINI_RATE_LIMIT_COOLDOWN)}s."
    )


def _call_gemini(prompt: str) -> str:
    """Run one Gemini call, tracking rate-limit cooldown. Raises if the
    backend is currently cooling down or the call fails."""
    if _gemini_on_cooldown():
        raise RuntimeError("Gemini is on rate-limit cooldown.")
    try:
        return make_gemini_executor()(prompt)
    except Exception as exc:  # noqa: BLE001 — cooldown on provider quota errors
        if _is_rate_limit_error(exc):
            _mark_gemini_rate_limited()
        raise


def _call_omniroute(prompt: str) -> str:
    from omniroute import client

    return client.chat(prompt)


def _resilient_executor(first, second) -> Executor:
    """Try ``first`` then ``second``; raise RuntimeError only if both fail."""

    def _execute(prompt: str) -> str:
        last_error: Optional[Exception] = None
        for fn in (first, second):
            try:
                return fn(prompt)
            except Exception as exc:  # noqa: BLE001 — deliberate cross-backend fallback
                last_error = exc
        raise RuntimeError(f"All LLM backends failed. Last error: {last_error}")

    return _execute


def default_executor() -> Executor:
    """Return a resilient executor whose backend order is chosen by the
    ``LESSAN_LLM_BACKEND`` env var:

    - ``omniroute`` (default): free OpenRouter pool first, Gemini last
      resort — free and fast in development, never blocked by quota.
    - ``auto``: Gemini first, OmniRoute fallback (previous behaviour).
    - ``gemini``: Gemini only.

    Unknown values fall back to ``omniroute`` (with a warning).
    """
    mode = os.getenv("LESSAN_LLM_BACKEND", "omniroute").strip().lower()
    if mode == "auto":
        return _resilient_executor(_call_gemini, _call_omniroute)
    if mode == "gemini":
        return make_gemini_executor()
    if mode != "omniroute":
        print(
            f"[llm_backend] Unknown LESSAN_LLM_BACKEND={mode!r} — "
            f"using 'omniroute'."
        )
    return _resilient_executor(_call_omniroute, _call_gemini)
