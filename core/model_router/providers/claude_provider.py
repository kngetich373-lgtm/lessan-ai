"""Claude Provider — adapter for Anthropic Claude models."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("ClaudeProvider")


class ClaudeProvider(CloudProviderBase):
    """Anthropic Claude provider adapter with live model discovery."""

    provider_name = "claude"
    display_name = "Anthropic Claude"
    api_key_env = "ANTHROPIC_API_KEY"
    priority_default = 60
    context_length_default = 200000

    default_models = [
        {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 200000,
            "extra": {"reasoning": True, "long_context": True},
        },
        {
            "id": "claude-opus-4-20250514",
            "name": "Claude Opus 4",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 200000,
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
        """Fetch the Claude models visible to the configured Anthropic key."""
        if not self.api_key:
            return self._models_from_data(self.default_models)

        models = []
        after_id = None

        while True:
            params = {"limit": "100"}
            if after_id:
                params["after_id"] = after_id

            url = "https://api.anthropic.com/v1/models?" + urlencode(params)
            request = Request(
                url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "accept": "application/json",
                },
                method="GET",
            )

            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))

            for item in payload.get("data", []):
                model_id = item.get("id")
                if not model_id or self._should_skip(model_id):
                    continue

                known = next(
                    (m for m in self.default_models if m["id"] == model_id),
                    None,
                )
                lower = model_id.lower()
                models.append({
                    "id": model_id,
                    "name": item.get("display_name") or model_id,
                    "streaming": True,
                    "vision": bool((known or {}).get("vision", True)),
                    "tool_calling": True,
                    "context_length": (known or {}).get(
                        "context_length", self.context_length_default
                    ),
                    "extra": {
                        "type": item.get("type"),
                        "created_at": item.get("created_at"),
                        "reasoning": any(
                            token in lower for token in ("opus", "sonnet")
                        ),
                    },
                })

            if not payload.get("has_more"):
                break
            after_id = payload.get("last_id")
            if not after_id:
                break

        return self._models_from_data(models) or self._models_from_data(self.default_models)

    @staticmethod
    def _should_skip(model_id: str) -> bool:
        """Exclude non-chat/utility models if Anthropic exposes any."""
        lower = model_id.lower()
        return any(token in lower for token in ("embedding", "moderation"))
