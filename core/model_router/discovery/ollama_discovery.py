"""Ollama Discovery — automatic detection and registration of Ollama models."""

import json
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from core.logging import get_logger
from core.model_router.models import ModelCapabilities, ModelInfo, ProviderInfo, CostMetadata
from core.model_router.capabilities import (
    CAPABILITY_PYTHON, CAPABILITY_REACT, CAPABILITY_REASONING,
    CAPABILITY_GENERAL_CHAT, CAPABILITY_LONG_CONTEXT,
)

logger = get_logger("OllamaDiscovery")

DEFAULT_OLLAMA_URL = "http://localhost:11434"

# Model name patterns → capabilities mapping
MODEL_CAPABILITIES = {
    "qwen": [CAPABILITY_PYTHON, CAPABILITY_REASONING, CAPABILITY_GENERAL_CHAT],
    "deepseek": [CAPABILITY_PYTHON, CAPABILITY_REASONING, CAPABILITY_GENERAL_CHAT],
    "llama": [CAPABILITY_GENERAL_CHAT, CAPABILITY_REASONING],
    "mistral": [CAPABILITY_GENERAL_CHAT, CAPABILITY_REASONING],
    "gemma": [CAPABILITY_GENERAL_CHAT],
    "codellama": [CAPABILITY_PYTHON, "cpp", "java"],
    "phi": [CAPABILITY_GENERAL_CHAT, CAPABILITY_REASONING],
}


class OllamaDiscovery:
    """Discovers and registers Ollama models running locally."""
    
    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL) -> None:
        self._base_url = base_url.rstrip("/")
    
    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False
    
    def discover_models(self) -> List[ModelInfo]:
        """Discover available Ollama models.
        
        Returns:
            List of ModelInfo objects for discovered models.
        """
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            
            models = []
            for model_data in data.get("models", []):
                model_name = model_data.get("name", "")
                if not model_name:
                    continue
                
                # Infer capabilities from model name
                capabilities = self._infer_capabilities(model_name)
                
                # Extract size if available
                size_bytes = model_data.get("size", 0)
                context_length = 4096  # Default Ollama context
                
                models.append(ModelInfo(
                    id=model_name,
                    capabilities=capabilities,
                    context_length=context_length,
                    cost=CostMetadata(is_free=True),
                    extra={"name": model_name},
                ))
            
            logger.info(f"Discovered {len(models)} Ollama models")
            return models
        
        except Exception as exc:
            logger.warning(f"Failed to discover Ollama models: {exc}")
            return []
    
    def create_provider_info(self) -> Optional[ProviderInfo]:
        """Create ProviderInfo for Ollama with discovered models.
        
        Returns:
            ProviderInfo if Ollama is available, None otherwise.
        """
        if not self.is_available():
            return None
        
        models = self.discover_models()
        if not models:
            return None
        
        return ProviderInfo(
            name="ollama",
            models=models,
            capabilities=ModelCapabilities(
                streaming=True,
                tool_calling=False,
                vision=False,
            ),
            context_length=4096,
            supports_streaming=True,
            cost=CostMetadata(is_free=True),
            priority=10,  # High priority for local models
            is_local=True,
        )
    
    def _infer_capabilities(self, model_name: str) -> ModelCapabilities:
        """Infer capabilities from model name."""
        model_lower = model_name.lower()
        
        # Find matching capability set
        extra_caps = {}
        for pattern, caps in MODEL_CAPABILITIES.items():
            if pattern in model_lower:
                for cap in caps:
                    extra_caps[cap] = True
                break
        
        # All Ollama models support basic chat
        if not extra_caps:
            extra_caps[CAPABILITY_GENERAL_CHAT] = True
        
        return ModelCapabilities(
            streaming=True,
            tool_calling=False,
            vision=False,
            extra=extra_caps,
        )
