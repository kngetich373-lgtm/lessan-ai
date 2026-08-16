"""OpenAI Provider — adapter for OpenAI GPT models."""

import json
from urllib.request import Request, urlopen

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("OpenAIProvider")


class OpenAIProvider(CloudProviderBase):
    """OpenAI provider adapter with live model discovery."""

    provider_name = "openai"
    display_name = "OpenAI"
    api_key_env = "OPENAI_API_KEY"
    priority_default = 60
    context_length_default = 128000

    default_models = [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {"reasoning": True},
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {},
        },
    ]

    default_capabilities = {
        "streaming": True,
        "vision": True,
        "tool_calling": True,
        "reasoning": True,
    }

    def discover_models(self):
        """Fetch the account-visible OpenAI model catalogue.

        OpenAI's model-list endpoint does not expose every capability in a
        uniform way, so capabilities are conservatively inferred from model
        identifiers while the built-in catalogue remains the fallback.
        """
        if not self.api_key:
            return self._models_from_data(self.default_models)

        request = Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        models = []
        for item in payload.get("data", []):
            model_id = item.get("id")
            if not model_id or self._should_skip(model_id):
                continue
            lower = model_id.lower()
            known = next((m for m in self.default_models if m["id"] == model_id), None)
            models.append({
                "id": model_id,
                "name": model_id,
                "streaming": True,
                "vision": bool(known and known.get("vision")) or any(x in lower for x in ("4o", "vision")),
                "tool_calling": True,
                "context_length": (known or {}).get("context_length", self.context_length_default),
                "extra": {
                    "owned_by": item.get("owned_by"),
                    "created": item.get("created"),
                },
            })

        return self._models_from_data(models) or self._models_from_data(self.default_models)

    @staticmethod
    def _should_skip(model_id: str) -> bool:
        """Exclude non-chat utility models from the chat model catalogue."""
        lower = model_id.lower()
        return any(token in lower for token in ("embedding", "moderation", "whisper", "tts", "dall-e"))
