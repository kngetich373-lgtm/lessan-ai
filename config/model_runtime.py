"""Execute text requests against the model selected in Lessan's UI.

The realtime Gemini Live session remains responsible for microphone/voice
interaction. Text messages can be routed to any imported model without
replacing the existing live session.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"


def _config() -> dict:
    try:
        return json.loads(API_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _model_record(model_id: str) -> dict | None:
    for model in _config().get("models", []):
        if model.get("id") == model_id:
            return model
    return None


def _provider_record(provider_id: str) -> dict | None:
    for provider in _config().get("providers", []):
        if provider.get("id") == provider_id:
            return provider
    return None


def _gemini(prompt: str, model: str, system: str | None) -> str:
    from google import genai

    key = _config().get("gemini_api_key") or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise RuntimeError("Gemini API key is not configured in Settings.")
    client = genai.Client(api_key=key)
    contents = prompt if not system else f"System instructions:\n{system}\n\nUser:\n{prompt}"
    response = client.models.generate_content(model=model, contents=contents)
    return str(getattr(response, "text", "") or "").strip()


def _openai_compatible(prompt: str, model: str, provider: dict, system: str | None) -> str:
    base = str(provider.get("base_url") or "").rstrip("/")
    if not base:
        raise RuntimeError(f"Provider '{provider.get('id')}' has no base URL configured.")
    if provider.get("id") == "ollama" and base.endswith("/v1"):
        base = base[:-3]
    url = base + "/chat/completions"
    key = provider.get("api_key") or ""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = requests.post(
        url,
        headers=headers,
        json={"model": model, "messages": messages, "temperature": 0.7, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Invalid chat-completions response from {provider.get('id')}: {data}") from exc


def complete_selected_model(prompt: str, model: str, system: str | None = None) -> tuple[str, str, str]:
    """Return ``(text, provider_id, model_id)`` for the selected imported model."""
    record = _model_record(model)
    if not record:
        raise RuntimeError(f"Model '{model}' is not imported. Open Settings → Providers & Models and discover it first.")
    provider_id = str(record.get("provider") or "").lower()
    if provider_id == "gemini":
        text = _gemini(prompt, model, system)
    else:
        provider = _provider_record(provider_id)
        if not provider or not provider.get("enabled", True):
            raise RuntimeError(f"Provider '{provider_id}' is not configured or is disabled.")
        text = _openai_compatible(prompt, model, provider, system)
    return text, provider_id, model
