"""LM Studio gateway adapter — local LM Studio OpenAI-compatible endpoint."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class LMStudioAdapter(OpenAICompatibleAdapter):
    """Adapter for a local LM Studio server (OpenAI-compatible mode).

    LM Studio typically runs at http://localhost:1234.
    """

    gateway_type = "lmstudio"
    _BASE_URL = "http://localhost:1234/v1"
    _DEFAULT_MODEL = "gpt-4o-mini"

    def _env_key_name(self) -> str:
        return ""

    def _auth_headers(self, record):
        return {"Content-Type": "application/json"}

    def supports_images(self, record) -> bool:
        return True
