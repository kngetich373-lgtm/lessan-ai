"""Custom OpenAI-compatible gateway adapter.

For any OpenAI-compatible endpoint (e.g. a self-hosted vLLM, LM Studio
OpenAI-compatible mode, or a third-party proxy).  The base URL and
optional API key are supplied at connection time via ``GatewayConfig``.
"""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class CustomOpenAIAdapter(OpenAICompatibleAdapter):
    """Adapter for a user-configured OpenAI-compatible gateway."""

    gateway_type = "custom_openai"
    _BASE_URL = "http://localhost:1234/v1"
    _DEFAULT_MODEL = "gpt-4o-mini"

    def _env_key_name(self) -> str:
        return "OPENAI_API_KEY"
