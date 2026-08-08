"""LiteLLM gateway adapter — LiteLLM proxy OpenAI-compatible endpoint."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class LiteLLMAdapter(OpenAICompatibleAdapter):
    """Adapter for a LiteLLM proxy server (OpenAI-compatible mode).

    The LiteLLM proxy exposes the same ``/chat/completions`` and
    ``/models`` endpoints as OpenAI, so it is treated as
    OpenAI-compatible.
    """

    gateway_type = "litellm"
    _BASE_URL = "http://localhost:4000"
    _DEFAULT_MODEL = "gpt-4o-mini"

    def _env_key_name(self) -> str:
        return "LITELLM_API_KEY"
