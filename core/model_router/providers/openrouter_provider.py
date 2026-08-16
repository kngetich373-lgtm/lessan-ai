"""OpenRouter Provider — adapter for OpenRouter model aggregation."""

import json
from urllib.request import Request, urlopen

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("OpenRouterProvider")


class OpenRouterProvider(CloudProviderBase):
    """OpenRouter provider with live discovery and OpenAI-compatible chat."""

    provider_name = "openrouter"
    display_name = "OpenRouter"
    api_key_env = "OPENROUTER_API_KEY"
    api_base = "https://openrouter.ai/api/v1"
    chat_api_style = "openai"
    priority_default = 40
    context_length_default = 131072

    default_models = [
        {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Flash (Free)", "streaming": True, "vision": True, "tool_calling": True, "context_length": 131072, "extra": {"free": True, "reasoning": True}},
        {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B (Free)", "streaming": True, "tool_calling": True, "context_length": 131072, "extra": {"free": True}},
        {"id": "qwen/qwen-2.5-72b-instruct:free", "name": "Qwen 2.5 72B (Free)", "streaming": True, "tool_calling": True, "context_length": 131072, "extra": {"free": True}},
    ]

    default_capabilities = {"streaming": True, "vision": True, "tool_calling": True, "reasoning": True}

    def _auth_headers(self):
        headers = super()._auth_headers()
        headers.update({"HTTP-Referer": "https://lessan.ai", "X-Title": "Lessan AI"})
        return headers

    def discover_models(self):
        request = Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        models = []
        for item in payload.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            architecture = item.get("architecture") or {}
            modalities = " ".join(architecture.get("input_modalities") or []).lower()
            pricing = item.get("pricing") or {}
            prompt_price = self._per_million(pricing.get("prompt"))
            completion_price = self._per_million(pricing.get("completion"))
            models.append({
                "id": model_id,
                "name": item.get("name") or model_id,
                "streaming": True,
                "vision": "image" in modalities,
                "tool_calling": True,
                "context_length": item.get("context_length") or self.context_length_default,
                "max_output_tokens": item.get("top_provider", {}).get("max_completion_tokens", 0) or 0,
                "input_per_million": prompt_price,
                "output_per_million": completion_price,
                "extra": {
                    "free": prompt_price == 0.0 and completion_price == 0.0,
                    "architecture": architecture,
                    "supported_parameters": item.get("supported_parameters", []),
                    "created": item.get("created"),
                },
            })
        return self._models_from_data(models) or self._models_from_data(self.default_models)

    @staticmethod
    def _per_million(value) -> float:
        try:
            return float(value or 0.0) * 1_000_000.0
        except (TypeError, ValueError):
            return 0.0
