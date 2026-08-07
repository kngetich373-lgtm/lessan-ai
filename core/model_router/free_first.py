"""Free-First Strategy — prioritizes free providers before paid ones."""

from typing import Optional

from core.logging import get_logger
from core.model_router.models import CostMetadata, ProviderInfo

logger = get_logger("FreeFirstStrategy")

# Priority tiers for free-first routing
PRIORITY_LOCAL_FREE = 10    # Local models (Ollama, etc.)
PRIORITY_CLOUD_FREE = 30    # Cloud free models (OpenRouter free, Gemini free)
PRIORITY_PAID = 60          # Paid providers

FREE_SCORE_MULTIPLIER = 2.0 # Boost free providers in scoring


def apply_free_first_priority(info: ProviderInfo) -> int:
    """Calculate priority tier based on cost and locality.
    
    Lower numbers = higher priority.
    
    Returns:
        Priority value (0-100).
    """
    # Local models always get highest priority
    if info.is_local:
        return PRIORITY_LOCAL_FREE
    
    # Check if provider is free
    if info.cost and getattr(info.cost, 'is_free', False):
        return PRIORITY_CLOUD_FREE
    
    # Check if provider has free models
    has_free_models = any(
        model.cost and getattr(model.cost, 'is_free', False)
        for model in info.models
    )
    if has_free_models:
        return PRIORITY_CLOUD_FREE
    
    # Default to paid tier
    return PRIORITY_PAID


def boost_free_score(base_score: float, cost: Optional[CostMetadata]) -> float:
    """Apply free-first multiplier to score.
    
    Args:
        base_score: Original score (0.0-1.0).
        cost: Cost metadata for the provider/model.
    
    Returns:
        Boosted score (may exceed 1.0).
    """
    if cost is None:
        return base_score
    
    if getattr(cost, 'is_free', False):
        return base_score * FREE_SCORE_MULTIPLIER
    
    return base_score


def is_free_provider(info: ProviderInfo) -> bool:
    """Check if a provider offers free models."""
    if info.cost and getattr(info.cost, 'is_free', False):
        return True
    return any(
        model.cost and getattr(model.cost, 'is_free', False)
        for model in info.models
    )
