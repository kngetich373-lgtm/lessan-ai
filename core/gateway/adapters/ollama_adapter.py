"""Ollama gateway adapter — local Ollama OpenAI-compatible endpoint."""

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class OllamaAdapter(OpenAICompatibleAdapter):
    """Adapter for a local Ollama instance (OpenAI-compatible mode).

    Ollama typically runs at http://localhost:11434.  When the
    OpenAI-compatible ``/v1`` routes are enabled (via the
    ``OLLAMA_HOST`` env or the ollama serve proxy), the standard
    chat-completions API is available.
    """

    gateway_type = "ollama"
    _BASE_URL = "http://localhost:11434/v1"
    _DEFAULT_MODEL = "llama3"

    def _env_key_name(self) -> str:
        return ""

    def _auth_headers(self, record):
        # Ollama local does not require auth
        return {"Content-Type": "application/json"}

    def supports_reasoning(self, record) -> bool:
        return False

    def supports_embeddings(self, record) -> bool:
        return True

    @property
    def supports_local(self) -> bool:
        return True
