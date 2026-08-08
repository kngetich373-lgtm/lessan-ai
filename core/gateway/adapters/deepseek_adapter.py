"""DeepSeek gateway adapter — OpenAI-compatible DeepSeek API."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class DeepSeekAdapter(OpenAICompatibleAdapter):
    """Adapter for the DeepSeek API (deepseek-chat, deepseek-reasoner)."""

    gateway_type = "deepseek"
    _BASE_URL = "https://api.deepseek.com/v1"
    _DEFAULT_MODEL = "deepseek-chat"

    def _env_key_name(self) -> str:
        return "DEEPSEEK_API_KEY"

    def supports_reasoning(self, record) -> bool:
        return True
