"""Kimi/Moonshot gateway adapter — OpenAI-compatible with long context."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class KimiAdapter(OpenAICompatibleAdapter):
    """Adapter for the Moonshot Kimi API (kimi-latest, kimi-long-context)."""

    gateway_type = "kimi"
    _BASE_URL = "https://api.moonshot.ai/v1"
    _DEFAULT_MODEL = "kimi-latest"

    def _env_key_name(self) -> str:
        return "MOONSHOT_API_KEY"

    def supports_reasoning(self, record) -> bool:
        return True
