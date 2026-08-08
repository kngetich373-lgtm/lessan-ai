"""OpenAI gateway adapter — OpenAI official API."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class OpenAIAdapter(OpenAICompatibleAdapter):
    """Adapter for the OpenAI API (GPT-4o, GPT-4o-mini, etc.)."""

    gateway_type = "openai"
    _BASE_URL = "https://api.openai.com/v1"
    _DEFAULT_MODEL = "gpt-4o-mini"

    def _env_key_name(self) -> str:
        return "OPENAI_API_KEY"

    def supports_images(self, record) -> bool:
        return True
