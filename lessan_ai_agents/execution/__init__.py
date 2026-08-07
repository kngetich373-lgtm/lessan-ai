"""
Execution backends for the lessan_ai_agents framework.

The eleven role agents are architecture-only by default: wiring an
``executor`` (callable ``prompt -> str``) into a ``RoleAgent`` makes its
``_run`` send the rendered prompt to a real backend (LLM, test double,
CLI, ...) and return the output. ``llm_backend`` provides Lessan AI's
default LLM executor (Gemini with OmniRoute fallback) plus the parsing
helpers the orchestrator uses on prompt-driven output.
"""

from .llm_backend import default_executor, parse_json_response, strip_fences

__all__ = ["default_executor", "parse_json_response", "strip_fences"]
