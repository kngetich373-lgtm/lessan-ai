"""Ollama Provider — adapter for local Ollama models."""

import json
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

from core.model_router.base_provider import BaseModelProvider
from core.model_router.models import ModelCapabilities, ModelInfo, ProviderInfo, RouteRequest
from core.model_router.discovery.ollama_discovery import OllamaDiscovery
from core.logging import get_logger

logger = get_logger("OllamaProvider")


class OllamaProvider(BaseModelProvider):
    """Provider adapter for Ollama local models."""
    
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")
        self._discovery = OllamaDiscovery(base_url)
        self._cached_models: List[ModelInfo] = []
    
    @property
    def name(self) -> str:
        return "ollama"
    
    def available_models(self) -> List[ModelInfo]:
        if not self._cached_models:
            self._cached_models = self._discovery.discover_models()
        return self._cached_models
    
    def capabilities(self) -> Dict[str, Any]:
        return {
            "streaming": True,
            "vision": False,
            "tool_calling": False,
            "local": True,
        }
    
    def info(self) -> ProviderInfo:
        models = self.available_models()
        return ProviderInfo(
            name=self.name,
            models=models,
            capabilities=ModelCapabilities(streaming=True, vision=False, tool_calling=False),
            context_length=4096,
            supports_streaming=True,
            priority=10,
            is_local=True,
        )
    
    def complete(self, request: RouteRequest) -> str:
        model = request.model or (self.available_models()[0].id if self.available_models() else "llama2")
        
        try:
            payload = json.dumps({
                "model": model,
                "prompt": request.prompt,
                "system": request.system or "",
                "stream": False,
            }).encode("utf-8")
            
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("response", "")
        except Exception as exc:
            logger.error(f"Ollama request failed: {exc}")
            raise RuntimeError(f"Ollama provider failed: {exc}")
    
    def complete_stream(self, request: RouteRequest) -> Iterator[str]:
        model = request.model or (self.available_models()[0].id if self.available_models() else "llama2")
        
        try:
            payload = json.dumps({
                "model": model,
                "prompt": request.prompt,
                "system": request.system or "",
                "stream": True,
            }).encode("utf-8")
            
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                for line in response:
                    if line:
                        try:
                            data = json.loads(line.decode("utf-8"))
                            chunk = data.get("response", "")
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.error(f"Ollama streaming failed: {exc}")
            raise RuntimeError(f"Ollama streaming failed: {exc}")
    
    def check_health(self) -> bool:
        return self._discovery.is_available()
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "available": self.check_health(),
            "model_count": len(self.available_models()),
            "base_url": self._base_url,
        }
