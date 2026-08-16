"""Gemini Provider — adapter for Google Gemini models."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from typing import Any, Dict

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("GeminiProvider")


class GeminiProvider(CloudProviderBase):
    """Google Gemini provider adapter with live model discovery."""

    provider_name = "gemini"
    display_name = "Google Gemini"
    api_key_env = "GEMINI_API_KEY"
    priority_default = 40
    context_length_default = 128000

    default_models = [
        {
            "id": "gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {"reasoning": True, "free": True, "long_context": True},
        },
        {
            "id": "gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {"reasoning": True, "long_context": True},
        },
    ]

    default_capabilities = {
        "streaming": True,
        "vision": True,
        "tool_calling": True,
        "reasoning": True,
    }

    def discover_models(self):
        """Fetch Gemini models available to the configured API key."""
        if not self.api_key:
            return self._models_from_data(self.default_models)

        models = []
        page_token = None

        while True:
            params = {"key": self.api_key, "pageSize": "1000"}
            if page_token:
                params["pageToken"] = page_token

            url = "https://generativelanguage.googleapis.com/v1beta/models?" + urlencode(params)
            request = Request(url, headers={"accept": "application/json"}, method="GET")

            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))

            for item in payload.get("models", []):
                model_id = item.get("baseModelId") or item.get("name", "").removeprefix("models/")
                if not model_id or "generateContent" not in item.get("supportedGenerationMethods", []):
                    continue

                input_types = {str(value).lower() for value in item.get("supportedInputTypes", [])}
                known = next(
                    (m for m in self.default_models if m["id"] == model_id),
                    None,
                )
                models.append({
                    "id": model_id,
                    "name": item.get("displayName") or model_id,
                    "streaming": True,
                    "vision": bool((known or {}).get("vision", False)) or "image" in input_types,
                    "tool_calling": True,
                    "context_length": item.get("inputTokenLimit") or self.context_length_default,
                    "max_output_tokens": item.get("outputTokenLimit", 0),
                    "extra": {
                        "version": item.get("version"),
                        "description": item.get("description"),
                        "thinking": item.get("thinking", item.get("thinkingModel", False)),
                        "base_model_id": item.get("baseModelId"),
                        "supported_generation_methods": item.get("supportedGenerationMethods", []),
                    },
                })

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        return self._models_from_data(models) or self._models_from_data(self.default_models)

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status["free_tier"] = True
        return status
