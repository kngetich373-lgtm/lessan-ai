"""vLLM gateway adapter — vLLM OpenAI-compatible serving endpoint."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class VLLMAdapter(OpenAICompatibleAdapter):
    """Adapter for a vLLM server (OpenAI-compatible mode).

    vLLM typically runs at http://localhost:8000/v1 or a remote URL.
    """

    gateway_type = "vllm"
    _BASE_URL = "http://localhost:8000/v1"
    _DEFAULT_MODEL = "gpt-4o-mini"

    def _env_key_name(self) -> str:
        return ""

    def _auth_headers(self, record):
        return {"Content-Type": "application/json"}

    def supports_reasoning(self, record) -> bool:
        return False

    def supports_embeddings(self, record) -> bool:
        return True
