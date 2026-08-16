"""Provider credential resolution for environment and persistent settings."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


class CredentialStore:
    """Resolve provider secrets without leaking them into logs or metadata.

    Environment variables take precedence over the legacy persistent
    ``api_keys.json`` compatibility store. The store never returns secrets in
    diagnostic snapshots.
    """

    ENV_NAMES = {
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "qwen": "QWEN_API_KEY",
    }

    def __init__(self, config: Any) -> None:
        self._config = config

    def get(self, provider: str) -> Optional[str]:
        name = provider.strip().lower()
        env_name = self.ENV_NAMES.get(name)
        if env_name:
            value = os.environ.get(env_name)
            if value:
                return value.strip() or None

        try:
            value = self._config.get_api_key(name)
            if value:
                return str(value).strip() or None
        except Exception:
            pass
        return None

    def configured(self, provider: str) -> bool:
        return self.get(provider) is not None

    def configured_providers(self) -> Dict[str, bool]:
        return {name: self.configured(name) for name in self.ENV_NAMES}

    @staticmethod
    def mask(value: Optional[str]) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "•" * len(value)
        return f"{value[:4]}{'•' * max(4, len(value) - 8)}{value[-4:]}"
